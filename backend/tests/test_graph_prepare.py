import pytest

from app.graph import prepare
from app.nodes.prep.analysis import AnalysisReport
from app.schemas.state import Analysis, Claim, Requirement, SessionStatus, StepState
from app.store import Store

SECRET = "비밀서류원문ZZZ"


def make_record():
    store = Store()
    rec = store.create(resume_text=SECRET, job_posting_text="공고", job_description_text="직무", cover_letter_text="자소서")
    return store, rec, rec.state.session_id


def fake_analysis(seen=None):
    def run(llm, resume, posting, jd, cover, on_step=None):
        for step in ("read_posting", "read_resume", "link", "checkpoints"):
            on_step(step, "RUNNING", None)
            if seen is not None:
                seen.append(step)
            on_step(step, "DONE", f"{step} 완료")
        analysis = Analysis(
            requirements=[Requirement(requirement_id="RQ-001", text="LangGraph 경험", source_doc="job_posting", kind="SKILL")],
            claims=[Claim(claim_id="CL-001", source_doc="resume", text="RAG 정확도 20% 개선")],
        )
        return AnalysisReport(analysis=analysis)
    return run


def test_prepare_success(monkeypatch):
    store, rec, sid = make_record()
    monkeypatch.setattr(prepare, "run_analysis", fake_analysis())
    prepare.run_prepare(store, sid, llm=object())
    s = rec.state
    assert s.status == SessionStatus.READY
    assert [x.step_id for x in s.steps] == ["read_posting", "read_resume", "link", "checkpoints", "questions", "review"]
    assert all(x.state == StepState.DONE for x in s.steps)
    assert s.analysis.requirements[0].requirement_id == "RQ-001"
    assert [q.question_id for q in s.questions] == ["Q-1", "Q-2", "Q-3", "Q-4", "Q-5"]
    assert [q.type.value for q in s.questions] == ["INTRO", "BEHAVIOR", "BEHAVIOR", "TECH", "TECH"]


def test_prepare_passes_documents_in_order(monkeypatch):
    store, rec, sid = make_record()
    got = {}

    def run(llm, resume, posting, jd, cover, on_step=None):
        got.update(resume=resume, posting=posting, jd=jd, cover=cover)
        return AnalysisReport(analysis=Analysis())

    monkeypatch.setattr(prepare, "run_analysis", run)
    prepare.run_prepare(store, sid, llm=object())
    assert got == {"resume": SECRET, "posting": "공고", "jd": "직무", "cover": "자소서"}


def test_steps_progress_is_visible_during_analysis(monkeypatch):
    store, rec, sid = make_record()
    snapshots = []

    def run(llm, resume, posting, jd, cover, on_step=None):
        on_step("read_posting", "RUNNING", None)
        snapshots.append({x.step_id: x.state.value for x in rec.state.steps})
        on_step("read_posting", "DONE", "요구사항 3개 확인")
        snapshots.append({x.step_id: (x.state.value, x.detail) for x in rec.state.steps})
        return AnalysisReport(analysis=Analysis())

    monkeypatch.setattr(prepare, "run_analysis", run)
    prepare.run_prepare(store, sid, llm=object())
    assert snapshots[0]["read_posting"] == "RUNNING" and snapshots[0]["link"] == "PENDING"
    assert snapshots[1]["read_posting"] == ("DONE", "요구사항 3개 확인")
    assert rec.state.status == SessionStatus.READY


def test_unexpected_error_marks_failed_without_leaking_documents(monkeypatch):
    store, rec, sid = make_record()

    def boom(*a, **k):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(prepare, "run_analysis", boom)
    prepare.run_prepare(store, sid, llm=object())
    assert rec.state.status == SessionStatus.FAILED
    assert isinstance(rec.state.error, str) and SECRET not in rec.state.error


def test_unknown_session_is_ignored():
    prepare.run_prepare(Store(), "S-00000000", llm=object())


def test_questions_not_exposed_while_preparing(client, monkeypatch):
    import app.api.interviews as interviews
    monkeypatch.setattr(interviews, "run_prepare", lambda *a, **k: None)
    r = client.post("/api/interviews", data=dict(resume_text="a", job_posting_text="b", job_description_text="c",
                                                cover_letter_text="d", privacy_consent="true"))
    sid = r.json()["session_id"]
    assert client.get(f"/api/interviews/{sid}").json()["questions"] is None
