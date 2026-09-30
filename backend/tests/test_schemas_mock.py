import json
import re
from pathlib import Path

import pytest

from app.schemas.api import (
    InterviewStatusResponse,
    ReportResponse,
    SubmitAnswerResponse,
)
from app.validators.quotes import find_quote

MOCK = Path(__file__).resolve().parents[2] / "shared" / "mock"


def load(name):
    return json.loads((MOCK / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["session_preparing.json", "session_ready.json", "session_evaluating.json"])
def test_status_mock(name):
    InterviewStatusResponse.model_validate(load(name))


def test_answer_accepted_mock():
    data = load("answer_accepted.json")
    for key in ("in_progress", "last"):
        SubmitAnswerResponse.model_validate(data[key])


def test_report_mock_and_quotes():
    data = load("report.json")
    report = ReportResponse.model_validate(data)
    answers = {q.question_id: q.answer_text for q in report.questions}
    quotes = report.attitude.quotes + report.job_fit.quotes + report.consistency.quotes
    for q in quotes:
        assert answers[q.question_id][q.start:q.end] == q.text


def test_quote_offsets_refer_to_original_decomposed_unicode_text():
    source = "가abcdefgh"

    match = find_quote("abcdefgh", source)

    assert match is not None
    assert source[match.start:match.end] == match.text == "abcdefgh"


def test_questions_have_no_criteria():
    for name in ("session_ready.json", "session_evaluating.json"):
        for q in load(name)["questions"]:
            assert set(q) == {"question_id", "order", "type", "text"}


def test_id_patterns():
    data = load("report.json")
    assert re.match(r"^S-[0-9a-f]{8}$", data["session_id"])


def test_report_requirements_kept():
    from app.schemas.api import ReportResponse

    data = load("report.json")
    data["requirements"] = [{"requirement_id": "RQ-004", "text": "LangGraph 경험", "kind": "SKILL"}]
    report = ReportResponse.model_validate(data)
    assert report.requirements[0].requirement_id == "RQ-004"
    assert "requirements" in report.model_dump()
