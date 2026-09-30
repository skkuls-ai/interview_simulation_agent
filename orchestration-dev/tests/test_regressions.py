"""독립 코드 리뷰에서 나온 문제들의 회귀 테스트."""

from __future__ import annotations

import time

import pytest

from backend.interview.agents import StubInterviewAgents
from backend.interview.state import FollowUpDecision, PassRule, SessionConfig
from backend.service.session_service import SessionError, TemporaryFailure

from .conftest import BANK, LONG, default_answer, drive, full_consent, make_service
from .test_scenarios import SlowEval, mains, new_session


class FailOnce(StubInterviewAgents):
    def __init__(self, bank):
        super().__init__(bank)
        self.failed = False

    def decide_follow_up(self, *a, **kw):
        if not self.failed:
            self.failed = True
            raise RuntimeError("LLM 503")
        return super().decide_follow_up(*a, **kw)


def test_agent_error_retry_same_request_recovers(tmp_path):
    s = make_service(tmp_path, interview_agents=FailOnce(BANK))
    sid = new_session(s)
    p = s.start(sid)
    p = s.act(sid, {"action": "start"}).prompt
    p = s.act(sid, default_answer(p)).prompt
    body = {"text": "첫 답변입니다", "answer_duration_sec": 30, "sequence": p.sequence}
    with pytest.raises(TemporaryFailure):
        s.act(sid, body)
    nxt = s.act(sid, body).prompt  # 재전송: 멈춘 지점부터 이어서 처리
    assert nxt.type == "await_answer" and nxt.sequence > p.sequence
    th = s.interview_graph.get_state(s._cfg(sid)).values["threads"][p.thread_id]
    assert [t.text for t in th.turns if t.kind == "answer"] == ["첫 답변입니다"]
    s.shutdown()


def test_agent_error_is_recoverable_without_duplicate_answer(tmp_path):
    s = make_service(tmp_path, interview_agents=FailOnce(BANK))
    sid = new_session(s)
    p = s.start(sid)
    p = s.act(sid, {"action": "start"}).prompt          # 자기소개
    p = s.act(sid, default_answer(p)).prompt            # 첫 본 질문
    first = p.thread_id
    body = {"text": "첫 답변입니다", "answer_duration_sec": 30, "sequence": p.sequence}
    with pytest.raises(TemporaryFailure):
        s.act(sid, body)
    view = s.resume_view(sid)                            # 재개 화면에서 멈춘 지점 복구
    assert view.next_prompt.type == "await_answer" and view.next_prompt.sequence != p.sequence
    retry = s.act(sid, body)                             # 같은 요청 재전송
    assert retry.prompt.sequence == view.next_prompt.sequence  # 무시되고 현재 질문을 돌려줌
    th = s.interview_graph.get_state(s._cfg(sid)).values["threads"][first]
    assert [t.text for t in th.turns if t.kind == "answer"] == ["첫 답변입니다"]  # 두 번 기록되지 않음
    s.shutdown()


class ProbeThenSatisfied(StubInterviewAgents):
    """꼬리질문을 한도까지 쓰고, 마지막 답변에서 근거가 충분하다고 판단."""

    def decide_follow_up(self, question, thread, config, points, blueprint, candidate_context=None):
        if thread.follow_up_count < config.max_follow_ups:
            fu = [f for f in question.follow_ups if f.id not in thread.used_follow_up_ids]
            if fu:
                return FollowUpDecision(action="ask_follow_up", follow_up_id=fu[0].id, rationale="더 확인")
            return FollowUpDecision(action="ask_follow_up", generated_question="구체적으로요?", rationale="더 확인")
        return FollowUpDecision(action="close", rationale="마지막 답변으로 충분")


def test_full_answer_on_last_follow_up_does_not_trigger_extra_question(tmp_path):
    s = make_service(tmp_path, interview_agents=ProbeThenSatisfied(BANK))
    sid = new_session(s, consent=full_consent(documents=False), docs=False)
    prompts, done = drive(s, sid)
    assert len(mains(prompts)) == 8
    assert all(t["close_reason"] == "sufficient" for t in done["detail"]["threads"] if t["stage"] == "main")
    s.shutdown()


def test_late_evaluation_not_saved_after_abandon(tmp_path):
    slow = SlowEval(delay=0.5)
    s = make_service(tmp_path, eval_agents=slow)
    sid = new_session(s)
    p = s.start(sid)
    for _ in range(4):
        p = s.act(sid, default_answer(p)).prompt
    assert slow.started or s._futures[sid]
    s.abandon(sid)
    time.sleep(1.2)
    assert s.store.evaluations(sid) == {}
    s.shutdown()


def test_unasked_category_policy_fail_overrides_hold(tmp_path):
    s = make_service(tmp_path)
    cfg = SessionConfig(pass_rule=PassRule(unasked_category_policy="fail", min_average=1.0, hold_margin=5))
    sid = new_session(s, consent=full_consent(documents=False), config=cfg, docs=False)
    _, done = drive(s, sid, lambda p: {"text": LONG, "answer_duration_sec": 400} if p.type == "await_answer" else default_answer(p))
    assert done["detail"]["chro_decision"]["unasked_categories"] == ["leadership"]
    assert done["detail"]["chro_decision"]["decision"] == "fail"
    s.shutdown()


def test_repeat_requests_are_capped(service):
    sid = new_session(service, consent=full_consent(documents=False), docs=False)
    seen = []

    def answer(p):
        seen.append(p)
        if p.type == "await_answer" and p.stage == "main" and len(mains(seen)) == 1:
            return {"text": "질문을 다시 말씀해 주시겠어요?", "answer_duration_sec": 3}
        return default_answer(p)

    drive(service, sid, answer)
    first = mains(seen)[0].thread_id
    repeats = [p for p in seen if p.type == "await_answer" and p.thread_id == first and p.kind == "repeat"]
    assert len(repeats) == 2  # max_repeats_per_question 기본값


def test_double_start_rejected(service):
    sid = new_session(service)
    service.start(sid)
    with pytest.raises(SessionError):
        service.start(sid)


def test_nonverbal_never_used_for_pass_fail(service):
    cfg = SessionConfig(pass_rule=PassRule(include_nonverbal=True))
    sid = service.create_session(full_consent(), cfg)
    stored = SessionConfig.model_validate_json(service.store.session(sid)["config"])
    assert stored.pass_rule.include_nonverbal is False


# ------------------------------------------------------------------ 9월 28일 2차 리뷰


def test_guard_allows_ordinary_words_but_blocks_forbidden():
    from backend.interview.guards import check_generated

    for ok in ["팀 성과를 향상시키는 데 본인은 어떤 역할을 했나요?", "규칙을 지키는 것이 왜 중요했나요?",
               "조직을 변화시키는 과정에서 무엇이 어려웠나요?", "집안일과 병행한 프로젝트였나요?",
               "지식재산 관련 업무를 어떻게 처리했나요?", "매출 신장에 어떤 기여를 했나요?", "연세대와의 협업은 어땠나요?"]:
        assert check_generated(ok) is None, ok
    for bad in ["키가 어떻게 되시나요?", "재산은 어느 정도인가요?", "나이가 어떻게 되세요?", "집안 형편은 어떤가요?",
                "정치 성향을 말씀해 주세요", "연세가 어떻게 되시나요?", "결혼 계획이 있으신가요?"]:
        assert check_generated(bad) is not None, bad


def test_old_checkpoint_class_path_still_allowed():
    from backend.interview.serde import make_serializer

    allowed = make_serializer()._allowed_msgpack_modules
    assert ("backend.interview.state", "VerificationPoint") in allowed
    assert ("backend.interview.blueprint", "VerificationPoint") in allowed


def test_invalid_point_categories_are_fixed():
    from backend.interview.agents import StubAnalysisAgents
    from backend.interview.analysis_graph import build_analysis_graph
    from backend.interview.blueprint import VerificationPoint
    from backend.interview.state import SessionConfig

    from .conftest import JD, RESUME

    class BadCats(StubAnalysisAgents):
        def verification_points(self, company, requirements, experiences, links):
            return [VerificationPoint(id="x", claim="c", concern="k", category_codes=["성과역량", "positivity"])]

    bp = build_analysis_graph(BANK, BadCats()).invoke(
        {"config": SessionConfig(), "seed": 1, "jd_text": JD, "resume_text": RESUME})["blueprint"]
    assert bp.verification_points[0].category_codes == ["performance"]
    assert any("V1" in pq.verification_point_ids for cp in bp.plan for pq in cp.primary)


def test_representative_matches_final_score_and_retry_reason_kept():
    from .test_panel import Scripted, out, run

    ev = run([Scripted(out(3, strengths=["three"])), Scripted(out(4, strengths=["four"])),
              Scripted(out(5, quote="지어낸 인용문입니다 정말로"), out(5, quote="지어낸 인용문입니다 정말로"))])
    assert ev.score == 4 and ev.strengths == ["four"]
    assert any(i.startswith("1차:") for i in ev.panel[2].issues)


def test_ask_at_limit_is_never_sufficient(tmp_path):
    """한도에서 '더 묻고 싶다'고 하면서 SUFFICIENT 를 붙여도 근거 부족으로 처리 (추가 문항 대상)."""
    from backend.interview.llm_agents import HybridInterviewAgents
    from backend.interview.state import AnswerQuality

    from .test_follow_up_judge import FakeLLM

    class AlwaysAsk(FakeLLM):
        def generate_json(self, role, system, prompt, schema):
            return super().generate_json(role, system, prompt, schema) if False else (
                schema.model_validate({
                    "covered": [], "missing": ["result"], "covered_intent_ids": [], "action": "ask_follow_up",
                    "question_source": "generated", "follow_up_id": "", "generated_question": "결과는 어떠했나요?",
                    "verification_point_id": "", "quality": "SUFFICIENT", "inconsistency_note": "", "rationale": "x"}),
                None)

    s = make_service(tmp_path, interview_agents=HybridInterviewAgents(BANK, AlwaysAsk()))
    sid = s.create_session(full_consent(documents=False))
    s.analyze(sid, seed=1)
    _, done = drive(s, sid)
    mains_ = [t for t in done["detail"]["threads"] if t["stage"] == "main"]
    assert all(t["close_reason"] == "max_follow_ups" and t["quality"] == AnswerQuality.PARTIAL.value for t in mains_)
    assert sum(t["is_extra"] for t in mains_) == 4  # 영역마다 추가 문항
    s.shutdown()
