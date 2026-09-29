"""데모 샘플과 정답 라벨의 무결성 검사 (LLM 호출 없음, docs/04 계약 기준).

라벨의 인용이 원문에 없거나 참조가 틀리면 이후 탐지율 결과를 믿을 수 없으므로 먼저 확인합니다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DEMO = Path(__file__).parents[1] / "data" / "demo"
DOC_NAMES = ("resume", "job_posting", "job_description", "cover_letter")
DOCS = {name: (DEMO / f"{name}.txt").read_text(encoding="utf-8") for name in DOC_NAMES}
LABELS = json.loads((DEMO / "expected_points.json").read_text(encoding="utf-8"))
INPUTS = json.loads((DEMO / "sample_inputs.json").read_text(encoding="utf-8"))

QUOTED = (
    LABELS["expected_claims"]
    + LABELS["expected_gaps"]
    + LABELS["expected_talent"]
    + [dict(label_id=f"{t['label_id']}-{i}", **s) for t in LABELS["traps"] for i, s in enumerate(t["sources"])]
)


def test_documents_are_marked_as_demo():
    for name, text in DOCS.items():
        assert "데모용 가상" in text, f"{name} 에 데모용 표시가 없습니다"


def test_sample_inputs_match_text_files():
    # API 입력 형식(sample_inputs.json)과 사람이 읽는 txt 가 어긋나지 않게 합니다.
    for name in DOC_NAMES:
        assert INPUTS[f"{name}_text"] == DOCS[name], f"{name}_text 가 {name}.txt 와 다릅니다"


@pytest.mark.parametrize("label", QUOTED, ids=lambda l: l["label_id"])
def test_every_quote_exists_exactly_once(label):
    doc = DOCS[label["source_doc"]]
    assert doc.count(label["quote"]) == 1, f"{label['label_id']}: 원문에 정확히 한 번 있어야 함 {label['quote']!r}"


def test_label_ids_are_unique():
    ids = [l["label_id"] for l in LABELS["expected_claims"] + LABELS["expected_checkpoints"]
           + LABELS["expected_gaps"] + LABELS["expected_talent"] + LABELS["traps"]]
    assert len(ids) == len(set(ids))


def test_claim_types_are_in_contract():
    for c in LABELS["expected_claims"]:
        assert c["types"] and set(c["types"]) <= set(LABELS["claim_types"]), c["label_id"]
        assert c["source_doc"] in ("resume", "cover_letter")  # 주장은 이력서·자소서에서만
        assert c["priority"] in ("high", "medium", "low")


def test_checkpoints_reference_existing_claims():
    claim_ids = {c["label_id"] for c in LABELS["expected_claims"]}
    for cp in LABELS["expected_checkpoints"]:
        assert cp["claim_label_ids"] and set(cp["claim_label_ids"]) <= claim_ids, cp["label_id"]


def test_gaps_and_talent_come_from_posting_or_description():
    for g in LABELS["expected_gaps"] + LABELS["expected_talent"]:
        assert g["source_doc"] in ("job_posting", "job_description"), g["label_id"]


# ---------------------------------------------------------------- session_preparing.json (W-06)
# docs/04 §3.2 GET /api/interviews/{id} 응답 (PREPARING, 단계 진행 중)

PREPARING = json.loads((DEMO / "session_preparing.json").read_text(encoding="utf-8"))
PREP_STEP_IDS = ["read_posting", "read_resume", "link", "checkpoints", "questions", "review"]
PREP_LABELS = ["채용공고 읽는 중", "이력서·자소서 읽는 중", "공고와 경험 연결 중",
               "검증 포인트 찾는 중", "질문 준비 중", "질문 검수 중"]


def test_preparing_mock_has_contract_shape():
    assert set(PREPARING) == {"session_id", "status", "steps", "questions"}
    assert PREPARING["status"] == "PREPARING"
    assert PREPARING["questions"] is None  # READY 전에는 null
    assert PREPARING["session_id"].startswith("S-") and len(PREPARING["session_id"]) == 10


def test_preparing_steps_follow_screen3_order_and_labels():
    steps = PREPARING["steps"]
    assert [s["step_id"] for s in steps] == PREP_STEP_IDS
    assert [s["label"] for s in steps] == PREP_LABELS
    for s in steps:
        assert set(s) == {"step_id", "label", "state", "detail"}
        assert s["state"] in ("PENDING", "RUNNING", "DONE")


def test_preparing_steps_progress_in_order():
    # 완료 → 진행 중(최대 1개) → 대기 순서여야 화면 3이 자연스럽게 그려집니다.
    order = {"DONE": 0, "RUNNING": 1, "PENDING": 2}
    states = [order[s["state"]] for s in PREPARING["steps"]]
    assert states == sorted(states)
    assert states.count(1) <= 1


def test_preparing_details_only_on_first_two_done_steps():
    # 화면 3 정의: 완료 뒤 수치는 1·2단계에만 표시
    for i, s in enumerate(PREPARING["steps"]):
        if i < 2 and s["state"] == "DONE":
            assert s["detail"]
        else:
            assert s["detail"] is None


def test_preparing_mock_leaks_no_question_content():
    # 면접 전에는 질문·검증 포인트·평가 기준을 노출하지 않습니다.
    text = json.dumps(PREPARING, ensure_ascii=False)
    for word in ("criteria", "checkpoint_id", "claim_id", "question_id", "20%"):
        assert word not in text


def test_demo_scenario_matches_docs():
    # docs 고정 시나리오: 「RAG 검색 정확도를 20% 개선」이 Q-1, Q-4 와 연결
    s = LABELS["demo_scenario"]
    assert s["linked_questions"] == ["Q-1", "Q-4"]
    claims = {c["label_id"]: c for c in LABELS["expected_claims"]}
    assert all("20% 개선" in claims[i]["quote"] for i in ("C1", "C2"))
    assert "30%" not in DOCS["resume"] + DOCS["cover_letter"]
