import json
from pathlib import Path

import jsonschema

from .conftest import BANK, ROOT


def test_bank_matches_schema_and_counts():
    schema = json.loads((ROOT / "backend/question_bank/schema.json").read_text(encoding="utf-8"))
    data = json.loads((ROOT / "backend/question_bank/question_bank.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(data)
    assert len(BANK.questions) == 150
    assert [c.code for c in BANK.categories] == ["performance", "relationship", "adaptability", "leadership"]
    assert sum(len(q.follow_ups) for q in BANK.questions) == 841


def test_every_competency_has_a_behavioral_question():
    for cat in BANK.categories:
        for comp in cat.competencies:
            assert any(q.question_type.value == "behavioral" for q in BANK.by_competency(comp.code)), comp.name


def test_quality_flags():
    assert BANK.get("Q007").duplicate_of == "Q006"
    assert BANK.get("Q116").duplicate_of == "Q111"
    assert BANK.get("Q023").follow_ups_shared_with == "Q021"
    assert BANK.get("Q021").follow_ups_shared_with is None
    assert len(BANK.get("Q023").follow_ups) == 7  # 공유 꼬리질문도 사용
    q = BANK.get("Q016")
    assert "답변하지 못할 경우" not in q.text and q.fallback_text.startswith("사소한 경험이라도")
    assert all(q.duplicate_of is None for q in BANK.by_competency("achievement_drive"))
    assert len(BANK.quality_warnings) == 11
