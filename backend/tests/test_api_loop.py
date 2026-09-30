import json
from pathlib import Path

from app.schemas.api import ReportResponse

MOCK = Path(__file__).resolve().parents[2] / "shared" / "mock"
SAMPLE = json.loads((MOCK / "sample_inputs.json").read_text(encoding="utf-8"))


def form(**overrides):
    data = {k: v for k, v in SAMPLE.items() if k != "privacy_consent"}
    data["privacy_consent"] = "true"
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


def create(client, **overrides):
    return client.post("/api/interviews", data=form(**overrides))


def answer(client, sid, qid, **extra):
    data = {"question_id": qid, "duration_sec": "30.5", "timed_out": "false", **extra}
    return client.post(f"/api/interviews/{sid}/answers", data=data)


def test_full_loop(client):
    r = create(client)
    assert r.status_code == 201
    sid = r.json()["session_id"]
    assert r.json()["status"] == "PREPARING"

    ready = client.get(f"/api/interviews/{sid}").json()
    assert ready["status"] == "READY"
    assert [q["question_id"] for q in ready["questions"]] == ["Q-1", "Q-2", "Q-3", "Q-4", "Q-5"]
    for q in ready["questions"]:
        assert set(q) == {"question_id", "order", "type", "text"}  # criteria 등 노출 금지

    for i in range(1, 5):
        r = answer(client, sid, f"Q-{i}")
        assert r.status_code == 202
        assert r.json() == {"question_id": f"Q-{i}", "received": True,
                            "next_question_id": f"Q-{i + 1}", "status": "IN_PROGRESS"}
    last = answer(client, sid, "Q-5")
    assert last.status_code == 202
    assert last.json()["next_question_id"] is None and last.json()["status"] == "EVALUATING"

    assert client.get(f"/api/interviews/{sid}").json()["status"] == "COMPLETED"
    rep = client.get(f"/api/interviews/{sid}/report")
    assert rep.status_code == 200
    assert ReportResponse.model_validate(rep.json()).session_id == sid


def test_missing_doc(client):
    r = create(client, resume_text=None)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "MISSING_REQUIRED_DOC"
    assert r.json()["error"]["field"] == "resume"


def test_consent_required(client):
    r = create(client, privacy_consent="false")
    assert r.status_code == 422 and r.json()["error"]["code"] == "CONSENT_REQUIRED"


def test_file_extraction_failed(client):
    data = form(resume_text=None)
    r = client.post("/api/interviews", data=data, files={"resume_file": ("cv.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 422
    assert r.json()["error"] == {"code": "TEXT_EXTRACTION_FAILED", "message": r.json()["error"]["message"], "field": "resume"}


def test_txt_file_accepted(client):
    r = client.post("/api/interviews", data=form(resume_text=None),
                    files={"resume_file": ("cv.txt", "이력서 본문".encode(), "text/plain")})
    assert r.status_code == 201


def test_session_not_found(client):
    for path in ("/api/interviews/S-00000000", "/api/interviews/S-00000000/report"):
        r = client.get(path)
        assert r.status_code == 404 and r.json()["error"]["code"] == "SESSION_NOT_FOUND"
    assert answer(client, "S-00000000", "Q-1").status_code == 404


def test_report_not_ready(client):
    sid = create(client).json()["session_id"]
    r = client.get(f"/api/interviews/{sid}/report")
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_READY"


def test_unknown_question(client):
    sid = create(client).json()["session_id"]
    r = answer(client, sid, "Q-9")
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNKNOWN_QUESTION"


def test_resend_returns_same_response(client):
    sid = create(client).json()["session_id"]
    first = answer(client, sid, "Q-1").json()
    again = answer(client, sid, "Q-1")
    assert again.status_code == 202 and again.json() == first


def test_answer_before_ready(client, monkeypatch):
    import app.api.interviews as interviews
    monkeypatch.setattr(interviews, "run_prepare", lambda *a, **k: None)
    sid = create(client).json()["session_id"]
    assert client.get(f"/api/interviews/{sid}").json()["status"] == "PREPARING"
    r = answer(client, sid, "Q-1")
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_IN_PROGRESS"


def test_delivery_metrics_stored(client):
    from app.store import store
    sid = create(client).json()["session_id"]
    answer(client, sid, "Q-1", delivery_metrics=json.dumps({"measurable": True, "frontal_ratio": 0.8, "gaze_away_count": 2}))
    a = store.get(sid).state.answers[0]
    assert a.delivery.frontal_ratio == 0.8 and a.delivery.gaze_away_count == 2
