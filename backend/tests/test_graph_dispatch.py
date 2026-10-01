import app.graph as graph
from app.graph import evaluate, fake, prepare
from app.schemas.state import SessionStatus
from app.store import Store


def make_store():
    store = Store()
    rec = store.create(resume_text="a", job_posting_text="b", job_description_text="c", cover_letter_text="d")
    return store, rec


def test_fake_mode_uses_fake(monkeypatch):
    monkeypatch.setenv("INTERVIEW_GRAPH_MODE", "fake")
    called = []
    monkeypatch.setattr(fake, "run_prepare", lambda s, sid: called.append("fake"))
    monkeypatch.setattr(prepare, "run_prepare", lambda s, sid: called.append("real"))
    graph.run_prepare(Store(), "S-00000000")
    assert called == ["fake"]


def test_real_mode_uses_real_graph(monkeypatch):
    monkeypatch.setenv("INTERVIEW_GRAPH_MODE", "real")
    called = []
    monkeypatch.setattr(fake, "run_evaluate", lambda s, sid: called.append("fake"))
    monkeypatch.setattr(evaluate, "run_evaluate", lambda s, sid: called.append("real"))
    graph.run_evaluate(Store(), "S-00000000")
    assert called == ["real"]


def test_auto_mode_without_credentials_is_fake(monkeypatch):
    monkeypatch.setenv("INTERVIEW_GRAPH_MODE", "auto")
    for key in ("GOOGLE_CLOUD_PROJECT", "GEMINI_API_KEY", "LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("app.llm.settings.LLMSettings.from_env",
                        classmethod(lambda cls: cls(project=None, api_key=None, use_vertex=False)))
    from app.graph.llm_factory import graph_mode
    assert graph_mode() == "fake"


def test_auto_mode_with_project_is_real(monkeypatch):
    monkeypatch.setenv("INTERVIEW_GRAPH_MODE", "auto")
    monkeypatch.setattr("app.llm.settings.LLMSettings.from_env",
                        classmethod(lambda cls: cls(project="p", api_key=None, use_vertex=True)))
    from app.graph.llm_factory import graph_mode
    assert graph_mode() == "real"


def test_real_mode_without_credentials_marks_prepare_failed(monkeypatch):
    store, rec = make_store()

    def no_llm():
        raise RuntimeError("자격 정보 없음")

    monkeypatch.setattr(prepare, "get_llm", no_llm)
    prepare.run_prepare(store, rec.state.session_id)
    assert rec.state.status == SessionStatus.FAILED


def test_api_loop_through_real_graph(client, monkeypatch):
    """모드 real: 서류 분석·평가를 스텁으로 바꿔 API 한 바퀴가 진짜 그래프 경로로 도는지 확인한다."""
    from app.graph.mock_data import load
    from app.nodes.prep.analysis import AnalysisReport
    from app.schemas.state import Analysis, Question

    monkeypatch.setenv("INTERVIEW_GRAPH_MODE", "real")
    monkeypatch.setattr(prepare, "get_llm", lambda: object())
    monkeypatch.setattr(evaluate, "get_llm", lambda: object())
    monkeypatch.setattr(prepare, "run_analysis", lambda llm, *a, on_step=None, **k: AnalysisReport(
        analysis=Analysis(),
        competency_questions=[
            Question(question_id="Q-2", order=2, type="BEHAVIOR", text="역량 질문 1"),
            Question(question_id="Q-3", order=3, type="BEHAVIOR", text="역량 질문 2"),
        ],
        technical_questions=[
            Question(question_id="Q-4", order=4, type="TECH", text="기술 질문 1"),
            Question(question_id="Q-5", order=5, type="TECH", text="기술 질문 2"),
        ],
    ))
    monkeypatch.setattr(evaluate, "evaluate_state", lambda state, llm, on_step=None, **k: load("report.json"))

    sid = client.post("/api/interviews", data=dict(resume_text="a", job_posting_text="b", job_description_text="c",
                                                   cover_letter_text="d", privacy_consent="true")).json()["session_id"]
    assert client.get(f"/api/interviews/{sid}").json()["status"] == "READY"
    for i in range(1, 6):
        assert client.post(f"/api/interviews/{sid}/answers", data={"question_id": f"Q-{i}", "duration_sec": "5"}).status_code == 202
    assert client.get(f"/api/interviews/{sid}").json()["status"] == "COMPLETED"
    assert client.get(f"/api/interviews/{sid}/report").json()["session_id"] == sid
