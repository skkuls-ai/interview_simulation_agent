"""POST /api/interviews 서류 접수 (W-28 연결). 파일 형식별 추출과 오류 응답을 API 로 확인합니다 (docs/08 T-107·T-108·T-109)."""

from __future__ import annotations

import json
from pathlib import Path

from app.store import store
from tests.test_prep_documents import LINE, make_blank_pdf, make_docx, make_pdf

MOCK = Path(__file__).resolve().parents[2] / "shared" / "mock"
SAMPLE = json.loads((MOCK / "sample_inputs.json").read_text(encoding="utf-8"))


def form(**overrides):
    data = {k: v for k, v in SAMPLE.items() if k != "privacy_consent"}
    data["privacy_consent"] = "true"
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


def state_of(client, r):
    assert r.status_code == 201, r.json()
    return store.get(r.json()["session_id"]).state


def test_pdf_and_docx_uploads_are_extracted(client):
    files = {
        "resume_file": ("cv.pdf", make_pdf(LINE, "FastAPI와 React로 채팅 UI 구현 (4인 팀)"), "application/pdf"),
        "cover_letter_file": ("cl.docx", make_docx([LINE], table=[["기간", "역할"], ["2026.09", "팀 리드"]]),
                              "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    }
    s = state_of(client, client.post("/api/interviews", data=form(resume_text=None, cover_letter_text=None), files=files))
    assert LINE in s.resume_text
    assert LINE in s.cover_letter_text and "2026.09 | 팀 리드" in s.cover_letter_text


def test_windows_korean_txt_upload(client):
    files = {"job_description_file": ("jd.txt", LINE.encode("cp949"), "text/plain")}
    s = state_of(client, client.post("/api/interviews", data=form(job_description_text=None), files=files))
    assert s.job_description_text == LINE


def test_scanned_pdf_and_hwp_name_the_field(client):
    for field, name, data in (("resume", "scan.pdf", make_blank_pdf()), ("job_posting", "공고.hwp", b"HWP Document File")):
        r = client.post("/api/interviews", data=form(**{f"{field}_text": None}),
                        files={f"{field}_file": (name, data, "application/octet-stream")})
        assert r.status_code == 422
        err = r.json()["error"]
        assert err["code"] == "TEXT_EXTRACTION_FAILED" and err["field"] == field and "직접 입력" in err["message"]


def test_consent_is_checked_before_missing_documents(client):
    r = client.post("/api/interviews", data=form(resume_text=None, privacy_consent="false"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "CONSENT_REQUIRED"
