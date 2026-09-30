import threading
import time

import pytest

from app.graph import evaluate
from app.graph.mock_data import load
from app.schemas.state import Answer, SessionStatus, StepState, TranscriptStatus
from app.store import Store


def make_record(statuses=("DONE",) * 5):
    store = Store()
    rec = store.create(resume_text="a", job_posting_text="b", job_description_text="c", cover_letter_text="d")
    ready = load("session_ready.json")
    from app.schemas.state import Question
    rec.state.questions = [Question(**q) for q in ready["questions"]]
    rec.state.answers = [
        Answer(question_id=f"Q-{i + 1}", duration_sec=10, transcript="답변" if st == "DONE" else None,
               transcript_status=TranscriptStatus(st))
        for i, st in enumerate(statuses)
    ]
    rec.state.status = SessionStatus.EVALUATING
    return store, rec, rec.state.session_id


def stub_evaluator(calls=None):
    def run(state, llm, on_step=None, **kw):
        if calls is not None:
            calls.append(state)
        for step in ("attitude", "job_fit", "consistency"):
            on_step(step, "RUNNING")
        for step in ("attitude", "job_fit", "consistency", "compose"):
            on_step(step, "DONE")
        return load("report.json")
    return run


def fast(store, sid):
    evaluate.run_evaluate(store, sid, llm=object(), stt_wait_sec=1.0, poll_sec=0.02)


def test_evaluate_success(monkeypatch):
    store, rec, sid = make_record()
    monkeypatch.setattr(evaluate, "evaluate_state", stub_evaluator())
    fast(store, sid)
    assert rec.state.status == SessionStatus.COMPLETED
    assert rec.report_response.session_id == sid  # mock의 세션 ID가 아니라 실제 세션 ID
    assert rec.state.report is not None
    assert [s.step_id for s in rec.state.steps] == ["transcribe", "attitude", "job_fit", "consistency", "compose"]
    assert all(s.state == StepState.DONE for s in rec.state.steps)
    assert rec.state.steps[0].detail == "답변 5개 변환 완료"


def test_waits_for_pending_transcripts(monkeypatch):
    store, rec, sid = make_record(("DONE", "DONE", "DONE", "DONE", "PENDING"))
    calls = []
    monkeypatch.setattr(evaluate, "evaluate_state", stub_evaluator(calls))

    def finish_later():
        time.sleep(0.3)
        with store.lock:
            rec.state.answers[4].transcript = "늦게 끝난 답변"
            rec.state.answers[4].transcript_status = TranscriptStatus.DONE

    t = threading.Thread(target=finish_later)
    t.start()
    evaluate.run_evaluate(store, sid, llm=object(), stt_wait_sec=3.0, poll_sec=0.02)
    t.join()
    assert [a.transcript_status for a in calls[0].answers].count(TranscriptStatus.PENDING) == 0
    assert calls[0].answers[4].transcript == "늦게 끝난 답변"
    assert rec.state.status == SessionStatus.COMPLETED


def test_timeout_marks_pending_as_failed_and_continues(monkeypatch):
    store, rec, sid = make_record(("DONE", "DONE", "DONE", "DONE", "PENDING"))
    calls = []
    monkeypatch.setattr(evaluate, "evaluate_state", stub_evaluator(calls))
    evaluate.run_evaluate(store, sid, llm=object(), stt_wait_sec=0.2, poll_sec=0.02)
    assert calls[0].answers[4].transcript_status == TranscriptStatus.FAILED
    assert rec.state.status == SessionStatus.COMPLETED
    assert rec.state.steps[0].detail == "답변 5개 중 4개 변환"


def test_late_stt_does_not_change_evaluation_input(monkeypatch):
    store, rec, sid = make_record(("DONE", "DONE", "DONE", "DONE", "PENDING"))
    calls = []
    monkeypatch.setattr(evaluate, "evaluate_state", stub_evaluator(calls))
    evaluate.run_evaluate(store, sid, llm=object(), stt_wait_sec=0.1, poll_sec=0.02)
    with store.lock:
        rec.state.answers[4].transcript = "너무 늦은 답변"
        rec.state.answers[4].transcript_status = TranscriptStatus.DONE
    assert calls[0].answers[4].transcript is None  # 평가 입력은 스냅샷


def test_all_no_speech_still_completes(monkeypatch):
    store, rec, sid = make_record(("NO_SPEECH",) * 5)
    monkeypatch.setattr(evaluate, "evaluate_state", stub_evaluator())
    fast(store, sid)
    assert rec.state.status == SessionStatus.COMPLETED


def test_evaluator_exception_marks_failed(monkeypatch):
    store, rec, sid = make_record()

    def boom(*a, **k):
        raise RuntimeError("개인정보 답변 원문")

    monkeypatch.setattr(evaluate, "evaluate_state", boom)
    fast(store, sid)
    assert rec.state.status == SessionStatus.FAILED
    assert "원문" not in rec.state.error and rec.report_response is None


def test_invalid_report_marks_failed(monkeypatch):
    store, rec, sid = make_record()
    monkeypatch.setattr(evaluate, "evaluate_state", lambda *a, **k: {"attitude": {}})
    fast(store, sid)
    assert rec.state.status == SessionStatus.FAILED


def test_duplicate_call_does_not_evaluate_twice(monkeypatch):
    store, rec, sid = make_record()
    calls = []
    monkeypatch.setattr(evaluate, "evaluate_state", stub_evaluator(calls))
    fast(store, sid)
    fast(store, sid)
    assert len(calls) == 1


def test_unknown_session_is_ignored():
    evaluate.run_evaluate(Store(), "S-00000000", llm=object())


def test_real_evaluator_with_fake_llm():
    """E의 러너를 가짜 LLM으로 끝까지 돌려 그래프 배선(입력 변환, 결과 검증)을 확인한다."""
    from tests.test_evaluate_runner import FakeLLM, make_input

    inp = make_input()
    store = Store()
    rec = store.create(resume_text="a", job_posting_text="b", job_description_text="c", cover_letter_text="d")
    rec.state.questions, rec.state.answers, rec.state.analysis = inp.questions, inp.answers, inp.analysis
    rec.state.status = SessionStatus.EVALUATING
    evaluate.run_evaluate(store, rec.state.session_id, llm=FakeLLM(), stt_wait_sec=1.0, poll_sec=0.02)
    assert rec.state.status == SessionStatus.COMPLETED
    assert rec.report_response.job_fit.verdict.value in {"SUFFICIENT", "NEEDS_WORK", "INSUFFICIENT", "WITHHELD"}
