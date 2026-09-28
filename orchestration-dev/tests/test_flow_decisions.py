"""9월 28일 결정 사항: 서류 기반 검증 포인트, 자기소개 추가, 질문 검증, 답변 품질 5분류, INCONSISTENT 보류 제한."""

from __future__ import annotations

from backend.interview.agents import StubAnalysisAgents
from backend.interview.analysis_graph import MAX_PERSONALIZE_RETRIES, build_analysis_graph
from backend.interview.blueprint import QuestionValidation
from backend.interview.evaluation import stub_panel_agents
from backend.interview.llm_agents import LLMFollowUpJudge
from backend.interview.prompts.follow_up_judge import build_prompt
from backend.interview.state import AnswerQuality, SessionConfig, VerificationPoint

from .conftest import BANK, JD, LONG, RESUME, default_answer, drive, full_consent, make_service
from .test_follow_up_judge import BP, CFG, judge_with, thread
from .test_scenarios import mains, new_session


def analyze(agents=None, **docs):
    g = build_analysis_graph(BANK, agents or StubAnalysisAgents())
    return g.invoke({"config": SessionConfig(), "seed": 1, **docs})["blueprint"]


# ------------------------------------------------------------------ 검증 포인트


def test_verification_points_come_from_documents_and_are_assigned():
    bp = analyze(jd_text=JD, resume_text=RESUME)
    assert bp.verification_points and all(p.source == "documents" for p in bp.verification_points)
    assert all(p.category_codes for p in bp.verification_points)
    assigned = {pid for cp in bp.plan for pq in cp.primary for pid in pq.verification_point_ids}
    assert assigned == {p.id for p in bp.verification_points}  # 모든 포인트에 확인할 문항이 정해짐


def test_no_documents_no_points():
    assert analyze().verification_points == []


def test_intro_adds_only_new_points(tmp_path):
    s = make_service(tmp_path)
    sid = new_session(s)  # 서류 있음 → 서류 포인트가 먼저 있음
    doc_points = len(s.analyze(sid, seed=1).verification_points)

    def answer(p):
        if p.type == "await_answer" and p.stage == "intro":
            return {"text": "저는 전사 채용 개편 프로젝트를 주도했습니다.", "answer_duration_sec": 50}
        return default_answer(p)

    prompt = s.start(sid)
    for _ in range(3):
        prompt = s.act(sid, answer(prompt)).prompt
    points = s.interview_graph.get_state(s._cfg(sid)).values["verification_points"]
    intro_points = [p for p in points.values() if p.source == "intro"]
    assert len(points) == doc_points + 1 and len(intro_points) == 1
    assert intro_points[0].id == f"V{doc_points + 1}"  # 서류 포인트와 ID 가 겹치지 않음
    s.shutdown()


# ------------------------------------------------------------------ 질문 검증


class Personalizing(StubAnalysisAgents):
    """첫 개인화 문구와 재시도 문구를 정해 두고, 문구별로 검증 통과 여부를 정하는 가짜 분석 에이전트."""

    def __init__(self, first: str, retry: str, bad: set[str]):
        self.first, self.retry, self.bad, self.feedbacks = first, retry, bad, []

    def personalize(self, question, planned, experiences, requirements, feedback=None):
        self.feedbacks.append(feedback)
        return planned.model_copy(update={"personalized_text": self.retry if feedback else self.first})

    def validate_question(self, question, planned, experiences, requirements):
        ok = planned.personalized_text not in self.bad
        return QuestionValidation(passed=ok, jd_relevant=ok, grounded=True, intent_preserved=True, lawful=True,
                                  issues=[] if ok else ["JD 와 무관"])


def first_planned(bp):
    return bp.plan[0].primary[0]


def test_validation_passes_after_retry():
    agents = Personalizing("문구1", "문구2", bad={"문구1"})
    pq = first_planned(analyze(agents, jd_text=JD, resume_text=RESUME))
    assert pq.validation == "passed" and pq.personalized_text == "문구2"
    assert ["JD 와 무관"] in agents.feedbacks  # 떨어진 이유를 다음 개인화에 전달
    assert "1차 검증 실패: JD 와 무관" in pq.validation_notes


def test_validation_reverts_to_original_after_max_retries():
    agents = Personalizing("문구1", "문구2", bad={"문구1", "문구2"})
    pq = first_planned(analyze(agents, jd_text=JD, resume_text=RESUME))
    assert pq.validation == "reverted" and pq.personalized_text is None
    assert sum("검증 실패" in note for note in pq.validation_notes) == MAX_PERSONALIZE_RETRIES + 1


def test_code_guard_rejects_forbidden_personalization_without_llm():
    agents = Personalizing("결혼 준비와 병행한 경험을 말씀해 주세요", "결혼 이후의 경험을 말씀해 주세요", bad=set())
    pq = first_planned(analyze(agents, jd_text=JD, resume_text=RESUME))
    assert pq.validation == "reverted" and any("금지 주제" in n for n in pq.validation_notes)


# ------------------------------------------------------------------ 답변 품질


def test_judge_assigns_quality_on_close_and_keeps_inconsistency_note():
    j, llm = judge_with(
        {"action": "close", "quality": "INCONSISTENT", "inconsistency_note": "서류는 3년, 답변은 1년", "rationale": "x"},
        {"action": "close", "quality": "none", "rationale": "x"},
        {"action": "ask_follow_up", "question_source": "generated", "generated_question": "당시 역할은 무엇이었나요?",
         "quality": "SUFFICIENT", "rationale": "x"},
    )
    d = j.decide(BANK.get("Q006"), thread("Q006", "1년 했습니다."), CFG, [], BP, candidate_context="[서류 경험] 채용 3년")
    assert d.quality is AnswerQuality.INCONSISTENT and d.inconsistency_note == "서류는 3년, 답변은 1년"
    assert not d.evidence_sufficient
    assert "[서류 경험] 채용 3년" in llm.calls[0]["prompt"]
    d = j.decide(BANK.get("Q006"), thread("Q006", "네."), CFG, [], BP)
    assert d.quality is AnswerQuality.PARTIAL and "품질 표시가 없어" in d.rationale  # 표시 누락은 보수적으로
    d = j.decide(BANK.get("Q006"), thread("Q006", "네."), CFG, [], BP)
    assert d.quality is None  # 꼬리질문을 할 때는 품질을 붙이지 않음


def test_prompt_shows_point_source():
    p = VerificationPoint(id="V1", source="documents", claim="c", concern="k", category_codes=["performance"])
    prompt = build_prompt(BANK.get("Q006"), thread("Q006", "네."), 3, "normal", [p], None, "desc", "ctx")
    assert '"출처": "서류"' in prompt and "## 지원자 맥락" in prompt


def test_inconsistent_answer_caps_hold_and_flags_next_interview(tmp_path):
    class Five:
        def evaluate_thread(self, question, thread, blueprint, points):
            from backend.interview.state import ThreadEvaluation
            return ThreadEvaluation(thread_id=thread.thread_id, question_id=question.id,
                                    competency_code=question.competency_code, score=5, confidence=1)

        def evaluate_intro(self, intro, blueprint, check):
            from backend.interview.agents import StubEvaluationAgents
            return StubEvaluationAgents().evaluate_intro(intro, blueprint, check)

    s = make_service(tmp_path, eval_agents=Five())
    sid = new_session(s, consent=full_consent(documents=False), docs=False)
    seen = []

    def answer(p):
        seen.append(p)
        if p.type == "await_answer" and p.stage == "main" and p.kind == "main" and len(mains(seen)) == 2:
            return {"text": "앞에서 말씀드린 것과 달리 사실 그 프로젝트는 제가 맡지 않았습니다.", "answer_duration_sec": 30}
        if p.type == "await_answer" and p.stage == "main":
            return {"text": LONG, "answer_duration_sec": 40}
        return default_answer(p)

    _, done = drive(s, sid, answer)
    chro, fb = done["detail"]["chro_decision"], done["detail"]["final_feedback"]
    target = mains(seen)[1].thread_id
    assert chro["inconsistent_threads"] == [target]
    assert chro["average_score"] == 5 and chro["decision"] == "hold"  # 점수는 만점이지만 최대 보류
    assert fb["follow_up_risks"][0]["thread_id"] == target and "다음 면접" in fb["follow_up_risks"][0]["tip"]
    assert fb["answer_quality"]["INCONSISTENT"] == 1
    s.shutdown()


def test_full_session_with_stub_panel(tmp_path):
    s = make_service(tmp_path, eval_agents=stub_panel_agents(BANK))
    sid = new_session(s)
    _, done = drive(s, sid)
    evs = done["detail"]["evaluations"]
    assert all(len(e["panel"]) == 3 for e in evs.values() if e["panel"])
    assert "answer_quality" in done["detail"]["final_feedback"]
    s.shutdown()
