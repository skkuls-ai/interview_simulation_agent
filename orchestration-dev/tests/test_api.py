"""FastAPI 엔드포인트와 문서 추출 테스트."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.service.consent import CONSENT_VERSION
from backend.service.documents import DocumentError, extract_text

from .conftest import JD, LONG, RESUME, SHORT, make_service

CONSENT = {"version": CONSENT_VERSION, "microphone": True, "camera": False, "documents": True, "store_results": True}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(make_service(tmp_path))) as c:
        yield c


def make_docx(text: str) -> bytes:
    import docx

    d = docx.Document()
    for line in text.splitlines():
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def make_pdf(lines: list[str]) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i, line in enumerate(lines):
        c.drawString(72, 750 - 20 * i, line)
    c.save()
    return buf.getvalue()


def test_extract_text_formats():
    assert "채용 프로세스" in extract_text("r.docx", make_docx(RESUME))
    assert "recruiting" in extract_text("j.pdf", make_pdf(["Company: ABC", "Own the full recruiting process for 300 hires"]))
    with pytest.raises(DocumentError, match="지원하지 않는 형식"):
        extract_text("a.hwp", b"x" * 100)
    with pytest.raises(DocumentError, match="텍스트를 거의 추출하지 못했습니다"):
        extract_text("blank.pdf", make_pdf([]))


def test_consent_required_microphone(client):
    assert client.get("/consent").json()["version"] == CONSENT_VERSION
    r = client.post("/sessions", json={"consent": {**CONSENT, "microphone": False}})
    assert r.status_code == 422


def test_full_flow_over_http(client):
    sid = client.post("/sessions", json={"consent": CONSENT}).json()["session_id"]
    r = client.post(f"/sessions/{sid}/documents", data={"kind": "jd"}, files={"file": ("jd.txt", JD.encode())})
    assert r.status_code == 200
    r = client.post(f"/sessions/{sid}/documents", data={"kind": "resume"},
                    files={"file": ("resume.docx", make_docx(RESUME))})
    assert r.status_code == 200 and r.json()["chars"] > 30
    bad = client.post(f"/sessions/{sid}/documents", data={"kind": "resume"}, files={"file": ("r.hwp", b"x" * 50)})
    assert bad.status_code == 400

    analyzed = client.post(f"/sessions/{sid}/analyze", json={"target_role": "HR 채용 담당"}).json()
    assert analyzed["personalized"] and set(analyzed) == {"personalized", "guide"}  # 질문 내용 비공개

    prompt = client.post(f"/sessions/{sid}/start").json()
    assert prompt["type"] == "await_ready"
    assert client.get("/sessions").json()[0]["session_id"] == sid

    for _ in range(100):
        if prompt["type"] == "await_ready":
            body = {"action": "start"}
        elif prompt["type"] == "no_response":
            body = {"choice": "skip"}
        else:
            text = SHORT if prompt["stage"] == "main" and prompt["kind"] == "main" else LONG
            body = {"text": text, "answer_duration_sec": 40}
            if prompt["stage"] == "main" and prompt["sequence"] == 5:
                resume = client.get(f"/sessions/{sid}/resume").json()
                assert resume["discarded_partial_answer"] and resume["next_prompt"]["resumed"]
        res = client.post(f"/sessions/{sid}/actions", json=body).json()
        if res["completed"]:
            break
        prompt = res["prompt"]
    else:
        pytest.fail("면접이 끝나지 않음")

    listed = client.get("/results").json()
    assert listed[0]["session_id"] == sid and listed[0]["decision"] in ("pass", "hold", "fail")
    detail = client.get(f"/results/{sid}").json()["detail"]
    assert detail["final_feedback"]["time_management"]["messages"]
    assert client.get(f"/sessions/{sid}/resume").status_code == 400  # 끝난 세션은 재개 불가
    assert client.delete(f"/results/{sid}").json()["ok"]
    assert client.get("/results").json() == []


def test_wrong_action_for_current_step(client):
    sid = client.post("/sessions", json={"consent": {**CONSENT, "documents": False}}).json()["session_id"]
    client.post(f"/sessions/{sid}/analyze", json={})
    client.post(f"/sessions/{sid}/start")
    r = client.post(f"/sessions/{sid}/actions", json={"text": "안녕하세요", "answer_duration_sec": 3})
    assert r.status_code == 422
    assert client.post(f"/sessions/{sid}/actions", json={"action": "start"}).json()["prompt"]["stage"] == "intro"
