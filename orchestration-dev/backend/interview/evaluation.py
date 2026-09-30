"""평가 패널: 같은 기준으로 3번 독립 채점 → 코드 검증 → 검증 에이전트 → 무효 평가자 1회 재평가 → 중앙값.

    평가자 ×3 (병렬) ─→ 코드 검증 ─→ 검증 에이전트 ─┬→ 모두 유효 ─────────────────→ 합치기
                                                 └→ 무효 평가자만 1회 재평가 → 코드 검증 → 검증 에이전트 → 합치기

합치기 규칙
- 유효 평가자 점수의 중앙값 (2명이면 평균을 반올림)
- 유효 평가자 1명 이하: 판단 보류 (score=None, status=undetermined)
- 유효 점수 간 차이가 2점 이상: status=disputed (점수는 중앙값을 쓰고 리포트에 표시)

그래프 밖 세션 서비스의 백그라운드 스레드에서 실행됩니다. LLM 동시 호출 수는 LLMGate 로 제한해
실시간 꼬리질문 판단이 호출 한도에 밀리지 않게 합니다.
"""

from __future__ import annotations

import logging
import math
import re
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from typing import Protocol

from ..llm.client import JsonLLM, LLMError
from ..question_bank.models import Question, QuestionBank
from .agents import StubEvaluationAgents
from .blueprint import InterviewBlueprint
from .prompts import evaluator as P
from .state import (
    CheckpointHit,
    IntroCheck,
    IntroEvaluation,
    PanelMember,
    QuestionThread,
    ThreadEvaluation,
    VerificationPoint,
    VerificationResult,
)

log = logging.getLogger(__name__)

PANEL_SIZE = 3
DISPUTE_GAP = 2
EVIDENCE_MATCH = 0.85


class LLMGate:
    """백그라운드 LLM 동시 호출 제한. 꼬리질문 판단(실시간)은 이 게이트를 쓰지 않아 항상 우선합니다."""

    def __init__(self, limit: int = 3):
        self._sem = threading.BoundedSemaphore(limit)

    def __enter__(self):
        self._sem.acquire()

    def __exit__(self, *exc):
        self._sem.release()


# ================================================================ 코드 검증

_norm_re = re.compile(r"[\s\.,!?'\"“”‘’·…~\-()\[\]]")


def _norm(text: str) -> str:
    return _norm_re.sub("", text)


def evidence_in(quote: str, source: str) -> bool:
    """인용이 지원자 발언에 있는지. 공백과 문장부호 차이는 무시하고, 거의 같은 발췌(85% 이상)도 인정."""
    q, s = _norm(quote), _norm(source)
    if len(q) < 4:
        return False
    if q in s:
        return True
    n = len(q)
    if n > len(s):
        return SequenceMatcher(None, q, s).ratio() >= EVIDENCE_MATCH
    step = max(1, n // 10)
    return any(SequenceMatcher(None, q, s[i:i + n]).ratio() >= EVIDENCE_MATCH for i in range(0, len(s) - n + 1, step))


def check_output(out: P.EvaluatorOutput, question: Question, thread: QuestionThread,
                 points: list[VerificationPoint]) -> list[str]:
    """평가 결과의 형식과 근거를 코드로 검사합니다. 문제 목록을 돌려주며, 비어 있으면 유효."""
    issues: list[str] = []
    said = " ".join(t.text for t in thread.turns if t.speaker == "candidate" and t.kind == "answer")
    pos_ids = {c.id for c in question.checkpoints.positive}
    neg_ids = {c.id for c in question.checkpoints.negative}
    valid_pos = 0
    for h in out.positive_hits:
        if h.checkpoint_id not in pos_ids:
            issues.append(f"positive_hits 에 Positive 체크포인트가 아닌 ID ({h.checkpoint_id})")
        elif not evidence_in(h.evidence, said):
            issues.append(f"{h.checkpoint_id} 근거가 지원자 발언에 없음: '{h.evidence[:40]}'")
        else:
            valid_pos += 1
    valid_neg = 0
    for h in out.negative_hits:
        if h.checkpoint_id not in neg_ids:
            issues.append(f"negative_hits 에 Negative 체크포인트가 아닌 ID ({h.checkpoint_id})")
        elif not evidence_in(h.evidence, said):
            issues.append(f"{h.checkpoint_id} 근거가 지원자 발언에 없음: '{h.evidence[:40]}'")
        else:
            valid_neg += 1
    dup = {h.checkpoint_id for h in out.positive_hits} & {h.checkpoint_id for h in out.negative_hits}
    if dup:
        issues.append(f"같은 체크포인트를 긍정과 부정에 동시 사용: {sorted(dup)}")
    if out.score >= 4 and valid_pos == 0:
        issues.append(f"{out.score}점인데 근거 있는 Positive 체크포인트가 없음")
    if out.score <= 2 and valid_neg == 0 and not out.improvements:
        issues.append(f"{out.score}점인데 Negative 근거나 개선점이 없음")
    intent_ids = {i.id for i in question.intents}
    bad_intents = [i for i in out.covered_intent_ids if i not in intent_ids]
    if bad_intents:
        issues.append(f"없는 질문 의도 ID: {bad_intents}")
    point_ids = {p.id for p in points}
    bad_points = [v.point_id for v in out.verification_results if v.point_id not in point_ids]
    if bad_points:
        issues.append(f"없는 검증 포인트 ID: {bad_points}")
    return issues


# ================================================================ 평가자, 검증 에이전트 인터페이스


class Evaluator(Protocol):
    def evaluate(self, question: Question, thread: QuestionThread, bp: InterviewBlueprint,
                 points: list[VerificationPoint], feedback: list[str] | None) -> P.EvaluatorOutput: ...


class Reviewer(Protocol):
    def review(self, question: Question, thread: QuestionThread, bp: InterviewBlueprint,
               members: list[tuple[int, P.EvaluatorOutput]]) -> dict[int, str | None]:
        """평가자 번호 → 무효 이유 (유효하면 None)."""
        ...


class GeminiEvaluator:
    def __init__(self, llm: JsonLLM, bank: QuestionBank, gate: LLMGate | None = None):
        self.llm, self.gate = llm, gate or LLMGate()
        self._desc = {c.code: c.description for cat in bank.categories for c in cat.competencies}

    def evaluate(self, question, thread, bp, points, feedback):
        prompt = P.evaluator_prompt(question, thread, bp, points, self._desc.get(question.competency_code, ""), feedback)
        with self.gate:
            out, _ = self.llm.generate_json("evaluator", P.EVALUATOR_SYSTEM, prompt, P.EvaluatorOutput)
        return out


class GeminiReviewer:
    def __init__(self, llm: JsonLLM, gate: LLMGate | None = None):
        self.llm, self.gate = llm, gate or LLMGate()

    def review(self, question, thread, bp, members):
        prompt = P.reviewer_prompt(question, thread, bp, members)
        with self.gate:
            out, _ = self.llm.generate_json("validator", P.REVIEWER_SYSTEM, prompt, P.ReviewOutput)
        wanted = {i for i, _ in members}
        result: dict[int, str | None] = {i: None for i in wanted}
        for item in out.items:
            if item.index in wanted and not item.valid:
                result[item.index] = item.reason or "검증 에이전트가 무효로 판정"
        return result


class GeminiIntroEvaluator:
    def __init__(self, llm: JsonLLM, gate: LLMGate | None = None):
        self.llm, self.gate = llm, gate or LLMGate()

    def evaluate(self, intro: QuestionThread, bp: InterviewBlueprint, check: IntroCheck | None) -> IntroEvaluation:
        with self.gate:
            out, _ = self.llm.generate_json("evaluator", P.INTRO_SYSTEM, P.intro_prompt(intro, bp), IntroEvaluation)
        return out


class StubEvaluator:
    """규칙 기반 평가자 (테스트용). 답변 분량으로 점수를 매기고, 첫 문장을 근거로 인용."""

    def evaluate(self, question, thread, bp, points, feedback):
        said = [t.text for t in thread.turns if t.speaker == "candidate" and t.kind == "answer"]
        total = sum(len(s) for s in said)
        score = max(1, min(5, total // 60))
        quote = said[-1][:30] if said else ""
        pos = [P.Hit(checkpoint_id=question.checkpoints.positive[0].id, evidence=quote)] if score >= 4 else []
        neg = [P.Hit(checkpoint_id=question.checkpoints.negative[0].id, evidence=quote)] if score <= 2 and quote else []
        return P.EvaluatorOutput(positive_hits=pos, negative_hits=neg, covered_intent_ids=[], verification_results=[],
                                 score=score, strengths=["(stub)"], improvements=["(stub) 결과 보강"], rationale="(stub)")


class StubReviewer:
    def review(self, question, thread, bp, members):
        return {i: None for i, _ in members}


# ================================================================ 패널


class EvaluationPanel:
    def __init__(self, evaluators: list[Evaluator], reviewer: Reviewer | None):
        self.evaluators = evaluators
        self.reviewer = reviewer

    def _run(self, idx: int, question, thread, bp, points, feedback=None) -> tuple[P.EvaluatorOutput | None, list[str]]:
        try:
            out = self.evaluators[idx].evaluate(question, thread, bp, points, feedback)
        except LLMError as e:
            return None, [f"평가 호출 실패: {str(e)[:80]}"]
        return out, check_output(out, question, thread, points)

    def _review(self, question, thread, bp, outs: dict[int, P.EvaluatorOutput]) -> dict[int, str | None]:
        if not self.reviewer or not outs:
            return {i: None for i in outs}
        try:
            return self.reviewer.review(question, thread, bp, sorted(outs.items()))
        except LLMError as e:
            # 검증 에이전트가 실패하면 코드 검증만 통과한 것으로 인정 (평가가 멈추지 않도록)
            log.warning("검증 에이전트 실패, 코드 검증 결과만 사용: %s", e)
            return {i: None for i in outs}

    def evaluate(self, question: Question, thread: QuestionThread, bp: InterviewBlueprint,
                 points: list[VerificationPoint]) -> ThreadEvaluation:
        n = len(self.evaluators)
        with ThreadPoolExecutor(max_workers=n) as pool:
            results = list(pool.map(lambda i: self._run(i, question, thread, bp, points), range(n)))
        outs: dict[int, P.EvaluatorOutput | None] = {i: r[0] for i, r in enumerate(results)}
        issues: dict[int, list[str]] = {i: list(r[1]) for i, r in enumerate(results)}

        # 1차 검증 에이전트: 코드 검증을 통과한 평가만 검토
        code_ok = {i: o for i, o in outs.items() if o is not None and not issues[i]}
        for i, reason in self._review(question, thread, bp, code_ok).items():
            if reason:
                issues[i].append(f"검증 에이전트: {reason}")

        # 무효 평가자만 1회 재평가
        retried = [i for i in range(n) if issues[i]]
        if retried:
            with ThreadPoolExecutor(max_workers=len(retried)) as pool:
                again = list(pool.map(lambda i: self._run(i, question, thread, bp, points, feedback=issues[i]), retried))
            second: dict[int, P.EvaluatorOutput] = {}
            history = {i: list(issues[i]) for i in retried}  # 재평가하게 된 이유는 기록에 남김
            for i, (out, errs) in zip(retried, again):
                outs[i] = out
                issues[i] = [f"재평가: {e}" for e in errs] if errs else []
                if out is not None and not errs:
                    second[i] = out
            for i, reason in self._review(question, thread, bp, second).items():
                if reason:
                    issues[i].append(f"재평가 후 검증 에이전트: {reason}")
        else:
            history = {}

        panel = [
            PanelMember(index=i, score=outs[i].score if outs[i] else None, valid=not issues[i],
                        re_evaluated=i in retried, issues=[*(f"1차: {h}" for h in history.get(i, [])), *issues[i]])
            for i in range(n)
        ]
        return self._combine(question, thread, panel, outs)

    @staticmethod
    def _combine(question: Question, thread: QuestionThread, panel: list[PanelMember],
                 outs: dict[int, P.EvaluatorOutput | None]) -> ThreadEvaluation:
        valid = [m for m in panel if m.valid and m.score is not None]
        base = dict(thread_id=thread.thread_id, question_id=question.id, competency_code=question.competency_code,
                    panel=panel)
        if len(valid) <= 1:
            return ThreadEvaluation(**base, score=None, status="undetermined", confidence=0.0,
                                    improvements=["평가자 간 합의가 이루어지지 않아 이 문항은 판단을 보류했습니다."])
        scores = [m.score for m in valid]
        median = statistics.median(scores)
        score = int(math.floor(median + 0.5))
        # 최종 점수와 같은 점수를 준 평가자를 대표로 (근거, 강점, 개선점이 점수와 맞도록)
        rep = min(valid, key=lambda m: (abs(m.score - score), m.index))
        o = outs[rep.index]
        status = "disputed" if max(scores) - min(scores) >= DISPUTE_GAP else "ok"
        return ThreadEvaluation(
            **base, score=score, status=status,
            positive_hits=[CheckpointHit(checkpoint_id=h.checkpoint_id, evidence=h.evidence) for h in o.positive_hits],
            negative_hits=[CheckpointHit(checkpoint_id=h.checkpoint_id, evidence=h.evidence) for h in o.negative_hits],
            covered_intent_ids=o.covered_intent_ids,
            verification_results=[VerificationResult(point_id=v.point_id, result=v.result, evidence=v.evidence)
                                  for v in o.verification_results],
            strengths=o.strengths, improvements=o.improvements,
            confidence=round(len(valid) / len(panel) * (1 - (max(scores) - min(scores)) / 4), 2),
        )


class PanelEvaluationAgents:
    """세션 서비스가 쓰는 EvaluationAgents 구현: 문항은 패널, 자기소개는 평가자 1명."""

    def __init__(self, bank: QuestionBank, panel: EvaluationPanel, intro_evaluator=None):
        self.bank = bank
        self.panel = panel
        self.intro_evaluator = intro_evaluator

    def evaluate_thread(self, question, thread, blueprint, points):
        return self.panel.evaluate(question, thread, blueprint, points)

    def evaluate_intro(self, intro, blueprint, check):
        if self.intro_evaluator is None:
            return StubEvaluationAgents().evaluate_intro(intro, blueprint, check)
        return self.intro_evaluator.evaluate(intro, blueprint, check)


def gemini_evaluation_agents(bank: QuestionBank, llm: JsonLLM, concurrency: int = 3) -> PanelEvaluationAgents:
    gate = LLMGate(concurrency)
    panel = EvaluationPanel([GeminiEvaluator(llm, bank, gate) for _ in range(PANEL_SIZE)], GeminiReviewer(llm, gate))
    return PanelEvaluationAgents(bank, panel, GeminiIntroEvaluator(llm, gate))


def stub_panel_agents(bank: QuestionBank) -> PanelEvaluationAgents:
    return PanelEvaluationAgents(bank, EvaluationPanel([StubEvaluator() for _ in range(PANEL_SIZE)], StubReviewer()))
