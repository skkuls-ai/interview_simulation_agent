"""데모 샘플과 정답 라벨의 무결성 검사 (LLM 호출 없음).

라벨의 인용이 원문에 없으면 이후 탐지율 실험 결과를 믿을 수 없으므로 먼저 확인합니다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DEMO = Path(__file__).parents[1] / "data" / "demo"
DOCS = {name: (DEMO / f"{name}.txt").read_text(encoding="utf-8") for name in ("jd", "resume", "cover_letter")}
LABELS = json.loads((DEMO / "expected_points.json").read_text(encoding="utf-8"))
ALL = LABELS["labels"] + LABELS["negative_labels"]


def test_documents_are_marked_as_demo():
    for name, text in DOCS.items():
        assert "데모용 가상" in text, f"{name} 에 데모용 표시가 없습니다"


@pytest.mark.parametrize("label", ALL, ids=lambda l: l["label_id"])
def test_every_quote_exists_in_its_source(label):
    for src in label["sources"]:
        assert src["doc"] in DOCS
        assert src["quote"] in DOCS[src["doc"]], f"{label['label_id']}: 원문에 없는 인용 {src['quote']!r}"


@pytest.mark.parametrize("label", ALL, ids=lambda l: l["label_id"])
def test_every_quote_is_unique_in_its_source(label):
    # 같은 문장이 두 번 나오면 어느 위치를 가리키는지 모호해집니다.
    for src in label["sources"]:
        assert DOCS[src["doc"]].count(src["quote"]) == 1, f"{label['label_id']}: 인용이 여러 번 등장 {src['quote']!r}"


def test_label_ids_are_unique():
    ids = [l["label_id"] for l in ALL]
    assert len(ids) == len(set(ids))


def test_claim_types_and_priorities_are_valid():
    for l in LABELS["labels"]:
        assert l["claim_type"] in LABELS["claim_types"]
        assert l["priority"] in {"high", "medium", "low"}


def test_every_claim_type_is_covered():
    # 데모에서 모든 유형의 검증 포인트를 보여줄 수 있어야 합니다.
    assert {l["claim_type"] for l in LABELS["labels"]} == set(LABELS["claim_types"])
