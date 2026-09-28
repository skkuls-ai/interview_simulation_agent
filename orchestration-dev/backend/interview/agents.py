"""에이전트 인터페이스와 LLM 없이 흐름을 검증하는 스텁 구현.

역할별로 세 묶음입니다.
- AnalysisAgents: 분석 그래프 (JD 분석, 경험 분석, 연결, 개인화, rubric)
- InterviewAgents: 면접 그래프 안 (자기소개 확인, 꼬리질문 판단, 관찰자, CHRO 근거, 종합 피드백)
- EvaluationAgents: 그래프 밖 백그라운드 (문항 평가, 자기소개 평가)

다음 단계에서 같은 인터페이스로 LLM 구현을 만들어 교체합니다.
"""

from __future__ import annotations

import re
from typing import Protocol

from ..question_bank.models import Question, QuestionBank, QuestionType
from .blueprint import (
    QuestionValidation,
    CompanyContext,
    Experience,
    InterviewBlueprint,
    IntroRubric,
    JDRequirement,
    PlannedQuestion,
    QuestionRubric,
    RequirementLink,
)
from .state import (
    AnswerElement,
    AnswerQuality,
    CHRODecision,
    CompetencyAdvice,
    DimensionScore,
    FinalFeedback,
    FollowUpDecision,
    IntroCheck,
    IntroEvaluation,
    IntroGuide,
    ObserverNote,
    ObserverReport,
    QuestionThread,
    SessionConfig,
    ThreadEvaluation,
    TimeReport,
    VerificationPoint,
    VerificationResult,
)

# ================================================================ 인터페이스


class AnalysisAgents(Protocol):
    def analyze_jd(self, jd_text: str) -> tuple[CompanyContext, list[JDRequirement]]: ...
    def analyze_experiences(self, resume_text: str | None, cover_letter_text: str | None) -> list[Experience]: ...
    def link(self, requirements: list[JDRequirement], experiences: list[Experience]) -> list[RequirementLink]: ...
    def verification_points(
        self, company: CompanyContext, requirements: list[JDRequirement], experiences: list[Experience],
        links: list[RequirementLink],
    ) -> list[VerificationPoint]:
        """서류에서 면접 중 확인할 주장을 뽑음 (근거가 약한 성과, JD 대비 공백, 서류 간 불일치 등)."""
        ...
    def personalize(
        self, question: Question, planned: PlannedQuestion, experiences: list[Experience],
        requirements: list[JDRequirement], feedback: list[str] | None = None,
    ) -> PlannedQuestion:
        """질문 문구를 지원자 경험에 맞게 다듬음. 평가 기준은 원본 문항을 따르므로 의도를 바꾸면 안 됨.
        feedback 이 있으면 이전 시도가 검증에서 떨어진 이유."""
        ...
    def validate_question(
        self, question: Question, planned: PlannedQuestion, experiences: list[Experience],
        requirements: list[JDRequirement],
    ) -> QuestionValidation: ...
    def question_rubric(self, question: Question, requirements: list[JDRequirement]) -> QuestionRubric: ...
    def intro_rubric(
        self, company: CompanyContext, requirements: list[JDRequirement], links: list[RequirementLink]
    ) -> IntroRubric: ...


class InterviewAgents(Protocol):
    def check_intro(
        self, intro: QuestionThread, blueprint: InterviewBlueprint, existing: list[VerificationPoint]
    ) -> IntroCheck:
        """자기소개 직후: 서류에 없던 주장, 서류와 어긋나는 말만 검증 포인트로 추가."""
        ...
    def decide_follow_up(
        self, question: Question, thread: QuestionThread, config: SessionConfig,
        pending_points: list[VerificationPoint], blueprint: InterviewBlueprint,
        candidate_context: str | None = None,
    ) -> FollowUpDecision:
        """candidate_context: 자기소개 요지와 서류 주요 경험 (INCONSISTENT 판단용)."""
        ...
    def observe(self, threads: list[QuestionThread]) -> ObserverReport: ...
    def chro_rationale(self, draft: CHRODecision, evaluations: list[ThreadEvaluation]) -> str: ...
    def final_feedback(
        self, decision: CHRODecision, evaluations: list[ThreadEvaluation], intro: IntroEvaluation | None,
        observer: ObserverReport | None, time_report: TimeReport,
    ) -> FinalFeedback: ...


class EvaluationAgents(Protocol):
    def evaluate_thread(
        self, question: Question, thread: QuestionThread, blueprint: InterviewBlueprint,
        points: list[VerificationPoint],
    ) -> ThreadEvaluation: ...
    def evaluate_intro(
        self, intro: QuestionThread, blueprint: InterviewBlueprint, check: IntroCheck | None
    ) -> IntroEvaluation: ...


# ================================================================ 스텁


class StubAnalysisAgents:
    """키워드 규칙으로 흉내만 냅니다. 실제 분석은 LLM 버전에서."""

    KEYWORDS = {
        "채용": ["planning", "execution"], "협업": ["collaboration"], "커뮤니케이션": ["communication"],
        "리더": ["organization_development"], "데이터": ["information_management", "problem_solving"],
        "고객": ["customer_orientation"], "변화": ["change_facilitation", "flexibility"],
    }

    def analyze_jd(self, jd_text):
        reqs = []
        lines = [l.strip("-• ").strip() for l in jd_text.splitlines() if l.strip() and not l.startswith("회사")]
        for i, line in enumerate(lines, 1):
            codes = sorted({c for k, v in self.KEYWORDS.items() if k in line for c in v})
            reqs.append(JDRequirement(
                id=f"R{i}", text=line[:80], kind="duty", importance="must" if i <= 3 else "preferred",
                competency_codes=codes,
            ))
        m = re.search(r"회사[:：]\s*(\S+)", jd_text)
        return CompanyContext(company_name=m.group(1) if m else None), reqs[:8]

    def analyze_experiences(self, resume_text, cover_letter_text):
        exps = []
        for src, text in (("resume", resume_text), ("cover_letter", cover_letter_text)):
            for line in (text or "").splitlines():
                line = line.strip("-• ").strip()
                if len(line) > 10:
                    codes = sorted({c for k, v in self.KEYWORDS.items() if k in line for c in v})
                    exps.append(Experience(
                        id=f"E{len(exps) + 1}", source=src, title=line[:30], summary=line, competency_codes=codes,
                    ))
        return exps[:10]

    def verification_points(self, company, requirements, experiences, links):
        req_by_id = {r.id: r for r in requirements}
        points = []
        for l in links:
            if l.strength == "gap" and l.requirement_id in req_by_id:
                r = req_by_id[l.requirement_id]
                points.append(VerificationPoint(
                    id=f"V{len(points) + 1}", source="documents", claim="서류상 직무 적합성 주장",
                    concern=f"'{r.text}' 관련 경험 근거가 서류에 부족", category_codes=[],
                    requirement_ids=[r.id],
                ))
        return points[:3]

    def validate_question(self, question, planned, experiences, requirements):
        from .guards import check_generated

        problem = check_generated(planned.personalized_text or "", max_chars=400)
        return QuestionValidation(passed=problem is None, jd_relevant=True, grounded=True, intent_preserved=True,
                                  lawful=problem is None, issues=[problem] if problem else [])

    def link(self, requirements, experiences):
        links = []
        for r in requirements:
            hit = [e.id for e in experiences if set(e.competency_codes) & set(r.competency_codes)]
            links.append(RequirementLink(
                requirement_id=r.id, experience_ids=hit,
                strength="strong" if len(hit) >= 2 else "partial" if hit else "gap",
                note="(stub) 키워드 기준 연결",
            ))
        return links

    def personalize(self, question, planned, experiences, requirements, feedback=None):
        return planned  # 스텁은 원본 문구 유지

    def question_rubric(self, question, requirements):
        ids = [c.id for c in question.checkpoints.positive + question.checkpoints.negative]
        related = [r.text for r in requirements if question.competency_code in r.competency_codes]
        return QuestionRubric(question_id=question.id, base_checkpoint_ids=ids, jd_criteria=related[:2])

    def intro_rubric(self, company, requirements, links):
        name = company.company_name or "이 회사"
        return IntroRubric(
            company_perspective=f"{name} 채용 담당자는 지원자가 왜 다른 회사가 아니라 {name}인지, 입사 후 무엇을 하려는지 듣고 싶어 함",
            criteria=[
                "이 회사여야만 하는 이유가 회사 고유의 사업, 가치, 직무 특성과 연결되는가",
                "제시한 경험이 JD 핵심 요구사항과 직접 연결되는가",
                "포부가 직무 범위 안에서 구체적이고 이력으로 뒷받침되는가",
            ],
            expected_links=[f"{l.requirement_id} ↔ {', '.join(l.experience_ids)}" for l in links if l.experience_ids][:3],
        )


class StubInterviewAgents:
    SHORT_ANSWER = 80

    def __init__(self, bank: QuestionBank):
        self.bank = bank

    def _categories_of(self, competency_codes: list[str]) -> list[str]:
        return [c.code for c in self.bank.categories if any(x.code in competency_codes for x in c.competencies)]

    def check_intro(self, intro, blueprint, existing):
        """스텁: 자기소개에 '주도'라는 말이 있으면 서류에 없던 리더십 주장으로 보고 검증 포인트를 하나 추가."""
        text = " ".join(t.text for t in intro.turns if t.kind == "answer")
        points = []
        if "주도" in text:
            points.append(VerificationPoint(
                id="new", source="intro", claim="(stub) 자기소개에서 프로젝트를 주도했다고 주장",
                concern="서류에 주도 경험의 근거가 없음", category_codes=["leadership"],
            ))
        return IntroCheck(verification_points=points)

    def decide_follow_up(self, question, thread, config, pending_points, blueprint, candidate_context=None):
        last = thread.turns[-1].text
        if "다시" in last and "말씀" in last:
            return FollowUpDecision(action="repeat_question", rationale="질문 반복 요청")
        if "앞에서 말씀드린 것과 달리" in last:
            return FollowUpDecision(action="close", quality=AnswerQuality.INCONSISTENT, evidence_sufficient=False,
                                    inconsistency_note="(stub) 앞선 답변과 다른 내용", rationale="모순")
        if "경험이 없" in last:
            fallback_used = any(t.text == question.fallback_text for t in thread.turns)
            if question.fallback_text and not fallback_used:
                return FollowUpDecision(action="ask_follow_up", generated_question=question.fallback_text,
                                        rationale="경험 없음, 원문의 대체 안내 사용")
            return FollowUpDecision(action="close", evidence_sufficient=False, quality=AnswerQuality.PARTIAL,
                                    rationale="관련 경험 없음")
        if pending_points and not any(t.verification_point_id for t in thread.turns):
            p = pending_points[0]
            return FollowUpDecision(
                action="ask_follow_up", verification_point_id=p.id,
                generated_question=f"그 부분과 관련해서, {_req_text(blueprint, p)} 경험을 조금 더 구체적으로 말씀해 주시겠습니까?",
                rationale="자기소개 검증 포인트 확인",
            )
        if len(last) >= self.SHORT_ANSWER:
            return FollowUpDecision(action="close", covered=[AnswerElement.ACTION, AnswerElement.RESULT],
                                    quality=AnswerQuality.SUFFICIENT, rationale="답변 충분")
        candidates = [f for f in question.follow_ups if f.id not in thread.used_follow_up_ids and f.kind is None]
        missing = [AnswerElement.RESULT] if question.question_type is QuestionType.BEHAVIORAL else [AnswerElement.REASON]
        if not candidates:
            return FollowUpDecision(action="ask_follow_up", generated_question="조금 더 구체적으로 말씀해 주시겠습니까?",
                                    missing=missing, rationale="원본 후보 소진")
        return FollowUpDecision(action="ask_follow_up", follow_up_id=candidates[0].id, missing=missing, rationale="답변이 짧음")

    def observe(self, threads):
        notes = []
        for th in threads:
            fillers = sum(t.speech.filler_count for t in th.turns if t.speech)
            if fillers:
                notes.append(ObserverNote(thread_id=th.thread_id, observation=f"군말 {fillers}회"))
        return ObserverReport(notes=notes, summary="(stub) 관찰 요약")

    def chro_rationale(self, draft, evaluations):
        return f"(stub) 평균 {draft.average_score:.2f}점, 판정 {draft.decision}"

    def final_feedback(self, decision, evaluations, intro, observer, time_report):
        weakest = sorted((e for e in evaluations if e.score is not None), key=lambda e: e.score)[:2]
        return FinalFeedback(
            headline=f"(stub) 종합 판정: {decision.decision}",
            strengths=[],
            improvements=[CompetencyAdvice(competency_code=e.competency_code, advice="(stub) 행동과 결과 보강") for e in weakest],
            intro_feedback=intro,
            time_management=time_report,
            next_practice_question_ids=[e.question_id for e in weakest],
        )


class StubEvaluationAgents:
    def evaluate_thread(self, question, thread, blueprint, points):
        total = sum(len(t.text) for t in thread.turns if t.speaker == "candidate" and t.kind == "answer")
        probed = {t.verification_point_id for t in thread.turns if t.verification_point_id}
        return ThreadEvaluation(
            thread_id=thread.thread_id, question_id=question.id, competency_code=question.competency_code,
            score=max(1, min(5, total // 60)), confidence=0.1, strengths=["(stub) 분량 기준"],
            verification_results=[
                VerificationResult(point_id=p, result="insufficient", evidence="(stub)") for p in sorted(probed)
            ],
        )

    def evaluate_intro(self, intro, blueprint, check):
        return IntroEvaluation(
            why_this_company=DimensionScore(score=3, comment="(stub)"),
            aspiration=DimensionScore(score=3, comment="(stub)"),
            experience_fit=DimensionScore(score=3, comment="(stub)"),
            summary="(stub) 자기소개 평가",
            guide=IntroGuide(motivation_points=["(stub)"], aspiration_points=["(stub)"],
                             suggested_outline=["경험 한 줄", "이 회사여야 하는 이유", "입사 후 포부"]),
        )


# ---------------------------------------------------------------- 공용


def _req_text(blueprint: InterviewBlueprint, point: VerificationPoint) -> str:
    reqs = {r.id: r.text for r in blueprint.requirements}
    return next((reqs[r] for r in point.requirement_ids if r in reqs), "해당 업무")


__all__ = [
    "AnalysisAgents", "InterviewAgents", "EvaluationAgents",
    "StubAnalysisAgents", "StubInterviewAgents", "StubEvaluationAgents",
]
