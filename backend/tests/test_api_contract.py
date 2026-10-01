"""08 문서 서버 항목 중 기존 테스트가 직접 덮지 않던 것 (T-208, T-209, T-212, T-219)."""
import tempfile
from pathlib import Path

import pytest

from tests.test_api_loop import answer, create

QIDS = ["Q-1", "Q-2", "Q-3", "Q-4", "Q-5"]
HIDDEN = ("criteria", "checkpoint_ids", "question_bank_id")


@pytest.mark.parametrize("field,key", [("resume", "resume_text"), ("job_posting", "job_posting_text"),
                                       ("job_description", "job_description_text"), ("cover_letter", "cover_letter_text")])
def test_t209_each_missing_doc_names_field(client, field, key):
    r = create(client, **{key: None})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "MISSING_REQUIRED_DOC" and r.json()["error"]["field"] == field


def test_t212_no_hidden_fields_in_any_response_during_interview(client):
    created = create(client)
    sid = created.json()["session_id"]
    bodies = [created.text, client.get(f"/api/interviews/{sid}").text]
    for qid in QIDS:
        bodies.append(answer(client, sid, qid).text)
        bodies.append(client.get(f"/api/interviews/{sid}").text)
    bodies.append(client.get("/api/interviews/S-00000000").text)
    for body in bodies:
        assert not any(word in body for word in HIDDEN)


def test_t208_video_is_not_stored(client):
    tmp = Path(tempfile.gettempdir())
    before = set(tmp.glob("*.webm")) | set(tmp.glob("*.mp4"))
    sid = create(client).json()["session_id"]
    r = client.post(f"/api/interviews/{sid}/answers",
                    data={"question_id": "Q-1", "duration_sec": "10", "timed_out": "false"},
                    files={"video": ("v.mp4", b"video-bytes", "video/mp4")})
    assert r.status_code == 202
    assert (set(tmp.glob("*.webm")) | set(tmp.glob("*.mp4"))) == before  # 영상은 받지도 저장하지도 않는다
    from app.store import store
    assert b"video-bytes" not in store.get(sid).state.model_dump_json().encode()


def test_t219_error_shape_is_uniform(client):
    sid = create(client).json()["session_id"]
    errors = [
        create(client, resume_text=None),
        create(client, privacy_consent="false"),
        client.get("/api/interviews/S-00000000"),
        client.get(f"/api/interviews/{sid}/report"),
        answer(client, sid, "Q-9"),
    ]
    codes = set()
    for r in errors:
        assert r.status_code >= 400
        err = r.json()["error"]
        assert set(err) >= {"code", "message"} and err["message"]
        codes.add(err["code"])
    assert codes == {"MISSING_REQUIRED_DOC", "CONSENT_REQUIRED", "SESSION_NOT_FOUND", "NOT_READY", "UNKNOWN_QUESTION"}
