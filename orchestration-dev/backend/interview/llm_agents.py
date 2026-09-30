"""LLM 에이전트 구현.

지금은 꼬리질문 판단만 LLM 이고, 나머지 역할은 스텁에 맡깁니다 (HybridInterviewAgents).
LLM 출력은 그대로 믿지 않고 코드 안전장치(sanitize)를 거칩니다.
"""

from __future__ import annotations

import logging
from ..llm.client import JsonLLM, LLMError
from ..question_bank.models import Question, QuestionBank, QuestionType
from .agents import StubInterviewAgents
from .blueprint import InterviewBlueprint
from .prompts import follow_up_judge as P
from .state import AnswerElement, AnswerQuality, FollowUpDecision, QuestionThread, SessionConfig, VerificationPoint

log = logging.getLogger(__name__)

BEHAVIORAL = {AnswerElement.SITUATION, AnswerElement.TASK, AnswerElement.ACTION, AnswerElement.RESULT, AnswerElement.LEARNING}
SITUATIONAL = {AnswerElement.JUDGMENT, AnswerElement.REASON, AnswerElement.ALTERNATIVE, AnswerElement.EXPECTED_OUTCOME}

from .guards import FORBIDDEN, MAX_QUESTION_CHARS, check_generated  # noqa: F401


class LLMFollowUpJudge:
    def __init__(self, llm: JsonLLM, bank: QuestionBank):
        self.llm = llm
        self.bank = bank
        self._descriptions = {c.code: c.description for cat in bank.categories for c in cat.competencies}
        self.last_call = None  # 평가 스크립트에서 지연 시간 확인용

    def decide(
        self, question: Question, thread: QuestionThread, config: SessionConfig,
        points: list[VerificationPoint], blueprint: InterviewBlueprint, candidate_context: str | None = None,
    ) -> FollowUpDecision:
        remaining = max(0, config.max_follow_ups - thread.follow_up_count)
        prompt = P.build_prompt(
            question, thread, remaining, config.pressure_level, points, blueprint.target_role,
            self._descriptions.get(question.competency_code, ""), candidate_context,
        )
        try:
            out, info = self.llm.generate_json("follow_up_judge", P.SYSTEM, prompt, P.JudgeOutput)
            self.last_call = info
        except LLMError as e:
            log.warning("꼬리질문 판단 LLM 실패, 기본 규칙 적용: %s", e)
            self.last_call = None
            return self.fallback(question, thread, remaining, reason=str(e))
        return self.sanitize(out, question, thread, remaining, points)

    # ------------------------------------------------------------ 안전장치

    def sanitize(
        self, out: P.JudgeOutput, question: Question, thread: QuestionThread, remaining: int,
        points: list[VerificationPoint],
    ) -> FollowUpDecision:
        notes: list[str] = []
        behavioral = question.question_type is QuestionType.BEHAVIORAL
        allowed = BEHAVIORAL if behavioral else SITUATIONAL
        covered = [e for e in out.covered if e in allowed]
        missing = [e for e in out.missing if e in allowed and e not in covered]
        intent_ids = {i.id for i in question.intents}
        covered_intents = [i for i in out.covered_intent_ids if i in intent_ids]
        point_ids = {p.id for p in points}
        vp = out.verification_point_id if out.verification_point_id in point_ids else None
        if out.verification_point_id and not vp:
            notes.append(f"없는 검증 포인트 {out.verification_point_id} 무시")

        action = out.action
        follow_up_id: str | None = None
        generated: str | None = None
        substituted = False

        if action == "ask_follow_up":
            usable = {f.id: f for f in question.follow_ups if f.id not in thread.used_follow_up_ids}
            fallback_unused = bool(question.fallback_text) and not any(
                t.text == question.fallback_text for t in thread.turns)

            if out.question_source == "fallback_text" and fallback_unused:
                generated = question.fallback_text
            elif out.follow_up_id and out.follow_up_id in usable:
                follow_up_id = out.follow_up_id
            elif out.generated_question.strip():
                problem = check_generated(out.generated_question)
                if problem is None:
                    generated = out.generated_question.strip()
                else:
                    notes.append(f"생성 질문 거부: {problem}")
            if out.follow_up_id and out.follow_up_id not in usable:
                notes.append(f"사용할 수 없는 꼬리질문 {out.follow_up_id}")
            if out.question_source == "fallback_text" and not fallback_unused:
                notes.append("대체 안내가 없거나 이미 사용함")

            if follow_up_id is None and generated is None:
                # 원본 후보를 기계적으로 고르면 맥락과 어긋날 수 있음 (첫 평가에서 확인).
                # 모델이 짚은 공백을 그대로 묻는 중립 질문으로 대체
                generated = element_question(missing, behavioral)
                substituted = True
                notes.append(f"질문이 비어 있어 기본 질문으로 대체: {generated}")

            if substituted and vp:
                vp = None  # 대체 질문은 검증 포인트와 무관

        quality: AnswerQuality | None = None
        note: str | None = None
        if action == "close" or (action == "ask_follow_up" and remaining == 0):
            if out.quality == "none":
                quality = AnswerQuality.PARTIAL
                notes.append("종료인데 품질 표시가 없어 PARTIAL 로 처리")
            else:
                quality = AnswerQuality(out.quality)
            if quality is AnswerQuality.INCONSISTENT:
                note = out.inconsistency_note.strip() or out.rationale.strip()

        rationale = out.rationale.strip() + (f" [보정: {'; '.join(notes)}]" if notes else "")
        return FollowUpDecision(
            action=action, covered=covered, missing=missing, covered_intent_ids=covered_intents,
            follow_up_id=follow_up_id, generated_question=generated,
            verification_point_id=vp if action == "ask_follow_up" else None,
            quality=quality, inconsistency_note=note,
            evidence_sufficient=(quality is AnswerQuality.SUFFICIENT) if quality else True,
            decided_by="llm", rationale=rationale,
        )

    def fallback(self, question: Question, thread: QuestionThread, remaining: int, reason: str) -> FollowUpDecision:
        """LLM 이 실패해도 면접이 멈추지 않도록 하는 기본 규칙: 꼬리질문은 한 번만, 본인 행동이나 이유를 확인."""
        note = f"LLM 실패로 기본 규칙 적용: {reason[:80]}"
        if remaining > 0 and thread.follow_up_count == 0:
            behavioral = question.question_type is QuestionType.BEHAVIORAL
            return FollowUpDecision(action="ask_follow_up", generated_question=element_question([], behavioral),
                                    decided_by="fallback", rationale=note)
        # 판단 근거가 없으므로 추가 문항을 유발하지 않도록 충분으로 둠
        return FollowUpDecision(action="close", evidence_sufficient=True, decided_by="fallback", rationale=note)


ELEMENT_QUESTIONS = {
    AnswerElement.ACTION: "그 상황에서 본인이 구체적으로 어떤 행동을 하셨는지 말씀해 주시겠습니까?",
    AnswerElement.RESULT: "그렇게 행동한 결과는 어떠했습니까?",
    AnswerElement.TASK: "그때 본인이 맡은 역할과 목표는 무엇이었습니까?",
    AnswerElement.SITUATION: "당시 상황을 조금 더 구체적으로 말씀해 주시겠습니까?",
    AnswerElement.LEARNING: "이 경험을 통해 배운 점은 무엇입니까?",
    AnswerElement.REASON: "그렇게 판단하신 이유는 무엇입니까?",
    AnswerElement.JUDGMENT: "그 상황에서 구체적으로 어떻게 하시겠습니까?",
    AnswerElement.ALTERNATIVE: "그 방법이 통하지 않는다면 어떻게 대응하시겠습니까?",
    AnswerElement.EXPECTED_OUTCOME: "그렇게 했을 때 예상되는 결과는 무엇입니까?",
}
PRIORITY_BEHAVIORAL = [AnswerElement.ACTION, AnswerElement.RESULT, AnswerElement.TASK,
                       AnswerElement.SITUATION, AnswerElement.LEARNING]
PRIORITY_SITUATIONAL = [AnswerElement.REASON, AnswerElement.JUDGMENT, AnswerElement.ALTERNATIVE,
                        AnswerElement.EXPECTED_OUTCOME]


def element_question(missing: list[AnswerElement], behavioral: bool) -> str:
    """가장 중요한 빠진 요소를 묻는 중립 질문. 빠진 요소를 모르면 본인 행동(경험)이나 이유(상황)를 묻습니다."""
    order = PRIORITY_BEHAVIORAL if behavioral else PRIORITY_SITUATIONAL
    target = next((e for e in order if e in missing), order[0])
    return ELEMENT_QUESTIONS[target]


class HybridInterviewAgents(StubInterviewAgents):
    """꼬리질문 판단만 LLM, 나머지는 스텁. 다른 에이전트를 구현하면 하나씩 교체합니다."""

    def __init__(self, bank: QuestionBank, llm: JsonLLM):
        super().__init__(bank)
        self.judge = LLMFollowUpJudge(llm, bank)

    def decide_follow_up(self, question, thread, config, pending_points, blueprint, candidate_context=None):
        return self.judge.decide(question, thread, config, pending_points, blueprint, candidate_context)
