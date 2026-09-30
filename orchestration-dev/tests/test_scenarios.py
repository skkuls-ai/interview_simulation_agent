"""시나리오 테스트: 면접 프로세스 요구사항을 하나씩 확인합니다.

    python -m pytest -q tests
"""

from __future__ import annotations

import threading
import time

import pytest

from backend.interview import phrases
from backend.interview.agents import StubEvaluationAgents
from backend.interview.blueprint import CATEGORY_NAMES
from backend.interview.state import Mode, SessionConfig
from backend.service.session_service import SessionError

from .conftest import BANK, JD, LONG, RESUME, SHORT, default_answer, drive, full_consent, make_service


def new_session(service, consent=None, config=None, docs=True):
    sid = service.create_session(consent or full_consent(), config)
    if docs:
        service.upload_document(sid, "jd", "jd.txt", JD.encode())
        service.upload_document(sid, "resume", "resume.txt", RESUME.encode())
    service.analyze(sid, target_role="HR 채용 담당", seed=1)
    return sid


def mains(prompts):
    return [p for p in prompts if p.type == "await_answer" and p.stage == "main" and p.kind == "main"]


# ------------------------------------------------------------------ 전체 흐름


def test_full_process_order_and_rules(service):
    sid = new_session(service)
    prompts, done = drive(service, sid)

    # 준비시간 → 자기소개 → 본 질문 → 마무리
    assert prompts[0].type == "await_ready"
    assert [i.topic for i in prompts[0].guide.items][0] == "자기소개"
    q_prompts = [p for p in prompts if p.type == "await_answer"]
    assert q_prompts[0].stage == "intro" and q_prompts[-1].stage == "closing"

    # 영역 순서: 성과 → 관계 → 적응 → 리더십, 영역별 2문항 (근거 충분하면 추가 없음)
    order = [BANK.get(p.thread_id).category_code for p in mains(prompts)]
    assert order == ["performance"] * 2 + ["relationship"] * 2 + ["adaptability"] * 2 + ["leadership"] * 2

    # 모든 질문에 준비 5초, 권장 1분
    assert all(p.think_time_sec == 5 and p.soft_limit_sec == 60 for p in q_prompts)

    # 전환 멘트에 영역 이름이 절대 없음
    names = list(CATEGORY_NAMES.values()) + ["성과", "관계", "적응", "리더십"]
    assert not any(n in (p.lead_in or "") for p in q_prompts for n in names)
    assert any(p.lead_in in phrases.FOLLOW_UP_LEAD_INS for p in q_prompts if p.kind == "follow_up")

    # 꼬리질문 최대 3회
    for th in done["detail"]["threads"]:
        n_fu = sum(1 for t in th["turns"] if t["kind"] in ("follow_up", "generated_follow_up"))
        assert n_fu <= 3

    # 평가: 본 질문 8개 + 자기소개 (자기소개와 마무리는 합불에 미반영)
    assert len(done["detail"]["evaluations"]) == 8
    assert done["detail"]["intro_evaluation"] is not None
    assert "intro" not in done["detail"]["evaluations"] and "closing" not in done["detail"]["evaluations"]
    assert done["summary"]["personalized"] is True


def test_guide_reveals_topics_counts_time_but_not_questions(service):
    sid = service.create_session(full_consent())
    service.upload_document(sid, "jd", "jd.txt", JD.encode())
    bp = service.analyze(sid, seed=1)
    guide_text = bp.guide.model_dump_json()
    for cp in bp.plan:
        for pq in cp.primary + cp.reserve:
            assert BANK.get(pq.question_id).text[:20] not in guide_text
    assert bp.guide.expected_minutes[0] < bp.guide.expected_minutes[1]


# ------------------------------------------------------------------ 문서, 동의, 삭제


def test_no_documents_path(service):
    sid = new_session(service, consent=full_consent(documents=False), docs=False)
    with pytest.raises(SessionError):
        service.upload_document(sid, "jd", "jd.txt", JD.encode())
    _, done = drive(service, sid)
    assert done["summary"]["personalized"] is False


def test_documents_deleted_after_session(service):
    sid = new_session(service)
    assert service.documents.exists(sid)
    drive(service, sid)
    assert not service.documents.exists(sid)
    row = service.store.session(sid)
    assert row["status"] == "completed" and row["documents_deleted_at"] and row["blueprint"] is None


def test_abandon_and_expire_delete_documents(tmp_path):
    from datetime import timedelta

    s = make_service(tmp_path)
    a = new_session(s)
    s.start(a)
    s.abandon(a)
    assert not s.documents.exists(a)

    b = new_session(s)
    s.session_ttl = timedelta(seconds=-1)
    assert b in s.purge_expired()
    assert not s.documents.exists(b)
    with pytest.raises(SessionError):
        s.resume_view(b)
    s.shutdown()


def test_results_saved_listed_deleted_only_with_consent(service):
    kept = new_session(service)
    drive(service, kept)
    not_kept = new_session(service, consent=full_consent(store_results=False))
    _, done = drive(service, not_kept)

    assert done["stored"] is False and done["detail"]["final_feedback"]  # 한 번은 보여줌
    ids = [r["session_id"] for r in service.list_results()]
    assert kept in ids and not_kept not in ids
    assert service.get_result(kept)["detail"]["time_report"]
    service.delete_result(kept)
    assert service.list_results() == []


# ------------------------------------------------------------------ 답변 규칙


def test_overtime_is_not_cut_and_is_reported(service):
    sid = new_session(service)

    def answer(p):
        if p.type == "await_answer" and p.stage == "main" and p.kind == "main":
            return {"text": LONG, "answer_duration_sec": 95}
        return default_answer(p)

    _, done = drive(service, sid, answer)
    tr = done["detail"]["time_report"]
    assert len(tr["overtime_answers"]) == 8
    assert all(o["overtime_sec"] == 35 for o in tr["overtime_answers"])
    assert any("초과 35초" in m for m in tr["messages"])


def test_no_response_retry_then_skip(service):
    sid = new_session(service)
    seen = []

    def answer(p):
        seen.append(p)
        first_main = mains(seen)[:1]
        if p.type == "await_answer" and first_main and p.thread_id == first_main[0].thread_id:
            return {"text": "  ", "answer_duration_sec": 60}  # 계속 무응답
        if p.type == "no_response":
            n = sum(1 for x in seen if x.type == "no_response")
            return {"choice": "retry" if n == 1 else "skip"}
        return default_answer(p)

    _, done = drive(service, sid, answer)
    nr = [p for p in seen if p.type == "no_response"]
    assert len(nr) == 2 and nr[0].message == "다시 답변하시겠어요?"
    retried = [p for p in seen if p.type == "await_answer" and p.lead_in == phrases.RETRY_LEAD_IN]
    assert len(retried) == 1
    skipped = mains(seen)[0].thread_id
    ev = done["detail"]["evaluations"][skipped]
    assert ev["score"] == 1


def test_extra_question_when_evidence_insufficient(service):
    sid = new_session(service)

    def answer(p):
        if p.type == "await_answer" and p.stage == "main" and p.kind == "main":
            cat = BANK.get(p.thread_id).category_code
            if cat == "relationship":
                return {"text": "그런 경험이 없습니다.", "answer_duration_sec": 10}
        return default_answer(p)

    prompts, done = drive(service, sid, answer)
    order = [BANK.get(p.thread_id).category_code for p in mains(prompts)]
    assert order.count("relationship") == 3  # 2 + 추가 1 (최대 1)
    assert order.count("performance") == 2
    extra = [t for t in done["detail"]["threads"] if t["is_extra"]]
    assert len(extra) == 1 and extra[0]["category_code"] == "relationship"


def _verbose(seconds):
    def answer(p):
        if p.type == "await_answer":
            return {"text": LONG, "answer_duration_sec": seconds}
        return default_answer(p)
    return answer


def test_verbose_candidate_loses_all_leadership_questions(service):
    # 문서 없이 진행해 문항당 답변 1회로 고정 (시간 계산을 단순하게)
    sid = new_session(service, consent=full_consent(documents=False), docs=False)
    prompts, done = drive(service, sid, _verbose(400))  # 매번 6분 40초: 자기소개 + 6문항에서 45분 초과
    cats = [BANK.get(p.thread_id).category_code for p in mains(prompts)]
    assert "leadership" not in cats
    assert prompts[-1].stage == "closing"  # 마무리 질문은 항상 함
    tr = done["detail"]["time_report"]
    assert tr["budget_exhausted"] and tr["unasked_categories"] == ["leadership"]
    assert tr["cut_categories"] == {"leadership": 2}
    assert any("답변이 장황해진 탓에 리더십역량 질문을 할 시간이 없었습니다" in m for m in tr["messages"])
    assert len(tr["overtime_answers"]) >= 5
    chro = done["detail"]["chro_decision"]
    assert chro["decision"] != "pass"
    assert any(c["name"] == "영역 평가 완료" and not c["passed"] for c in chro["rule_checks"])


def test_verbose_candidate_partially_loses_leadership(service):
    sid = new_session(service, consent=full_consent(documents=False), docs=False)
    prompts, done = drive(service, sid, _verbose(350))  # 매번 5분 50초: 리더십 1문항 후 45분 초과
    cats = [BANK.get(p.thread_id).category_code for p in mains(prompts)]
    assert cats.count("leadership") == 1
    tr = done["detail"]["time_report"]
    assert tr["unasked_categories"] == [] and tr["cut_categories"] == {"leadership": 1}
    assert any("리더십역량 1개" in m for m in tr["messages"])


def test_fallback_prompt_used_when_no_experience(service):
    """원문의 '(답변하지 못할 경우)' 안내는 경험이 없다고 할 때만 꼬리질문으로 나옴."""
    from backend.interview.state import SessionConfig

    sid = service.create_session(full_consent(documents=False))
    bp = service.analyze(sid, seed=1)
    # Q016 을 첫 문항으로 강제
    cp = bp.plan[0]
    q16 = cp.primary[0].model_copy(update={"question_id": "Q016", "competency_code": BANK.get("Q016").competency_code})
    bp.plan[0] = cp.model_copy(update={"primary": [q16, *cp.primary[1:]]})
    service.store.update_session(sid, blueprint=bp)

    def answer(p):
        if p.type == "await_answer" and p.thread_id == "Q016" and p.kind == "main":
            return {"text": "그런 경험이 없습니다.", "answer_duration_sec": 5}
        return default_answer(p)

    prompts, _ = drive(service, sid, answer)
    q16 = [p for p in prompts if p.type == "await_answer" and p.thread_id == "Q016"]
    assert "답변하지 못할 경우" not in q16[0].text
    assert q16[1].text == BANK.get("Q016").fallback_text


def test_intro_verification_points_are_probed_later(service):
    sid = new_session(service)
    prompts, done = drive(service, sid)
    vp_turns = [t for th in done["detail"]["threads"] for t in th["turns"] if t.get("verification_point_id")]
    assert vp_turns, "자기소개 검증 포인트를 확인하는 꼬리질문이 있어야 함"
    first = min(i for i, p in enumerate(prompts) if p.type == "await_answer" and p.stage == "main")
    assert prompts[first - 1].stage == "intro"


# ------------------------------------------------------------------ 백그라운드 평가


class SlowEval(StubEvaluationAgents):
    def __init__(self, delay: float):
        self.delay = delay
        self.started: list[str] = []
        self.lock = threading.Lock()

    def evaluate_thread(self, question, thread, blueprint, points):
        with self.lock:
            self.started.append(thread.thread_id)
        time.sleep(self.delay)
        return super().evaluate_thread(question, thread, blueprint, points)


def test_background_evaluation_does_not_block_interview(tmp_path):
    slow = SlowEval(delay=0.6)
    s = make_service(tmp_path, eval_agents=slow)
    sid = new_session(s)
    prompt = s.start(sid)
    worst = 0.0
    started_during_interview = False
    while True:
        t0 = time.perf_counter()
        res = s.act(sid, default_answer(prompt))
        if res.completed:
            break
        worst = max(worst, time.perf_counter() - t0)
        prompt = res.prompt
        if prompt.type == "await_answer" and prompt.stage == "closing":
            # 마무리 질문 시점에 본 질문 8개와 자기소개 평가가 모두 제출되었고, 일부는 이미 실행 중
            started_during_interview = len(s._futures[sid]) == 9 and len(slow.started) >= 1
    assert started_during_interview
    assert worst < 0.5  # 평가(0.6초)를 기다리지 않고 다음 질문이 나옴
    s.shutdown()


class FlakyEval(StubEvaluationAgents):
    def __init__(self):
        self.calls = 0

    def evaluate_thread(self, question, thread, blueprint, points):
        self.calls += 1
        if self.calls % 2 == 1:
            raise RuntimeError("일시 오류")
        return super().evaluate_thread(question, thread, blueprint, points)


def test_evaluation_retries_on_transient_error(tmp_path):
    s = make_service(tmp_path, eval_agents=FlakyEval())
    sid = new_session(s)
    _, done = drive(s, sid)
    assert len(done["detail"]["evaluations"]) == 8
    s.shutdown()


def test_practice_mode_pushes_question_feedback(tmp_path):
    events = []
    s = make_service(tmp_path, events=events)
    sid = new_session(s, config=SessionConfig(mode=Mode.PRACTICE))
    drive(s, sid)
    types = [ev.type for _, ev in events]
    assert types.count("question_feedback") == 8
    assert "interviewer_thinking" in types
    s.shutdown()


# ------------------------------------------------------------------ 중단 후 재개


def test_resume_after_server_restart(tmp_path):
    s1 = make_service(tmp_path)
    sid = new_session(s1)
    prompt = s1.start(sid)
    for _ in range(6):  # 준비 → 자기소개 → 본 질문 몇 개
        prompt = s1.act(sid, default_answer(prompt)).prompt
    assert prompt.type == "await_answer"
    s1.shutdown()  # 서버 종료 (진행 중 평가 작업은 사라질 수 있음)

    s2 = make_service(tmp_path)  # 같은 DB 로 재시작
    view = s2.resume_view(sid)
    assert view.discarded_partial_answer is True
    assert view.next_prompt.resumed and view.next_prompt.lead_in == phrases.RESUME_LEAD_IN
    assert view.next_prompt.text == prompt.text
    assert [st.title for st in view.steps][0] == "이전 면접을 이어서 진행합니다"
    assert sid in [x["session_id"] for x in s2.in_progress_sessions()]

    _, done = drive(s2, sid, first=view.next_prompt)
    assert len(done["detail"]["evaluations"]) == 8
    s2.shutdown()


def test_invalid_payload_rejected_without_state_change(service):
    sid = new_session(service)
    p = service.start(sid)
    with pytest.raises(Exception):
        service.act(sid, {"text": "시작"})  # 준비 단계인데 답변을 보냄
    assert service.current_prompt(sid).type == p.type
