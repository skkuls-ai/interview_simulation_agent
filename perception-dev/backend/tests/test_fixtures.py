import json
from pathlib import Path

from app.perception.schemas import PerceptionResult


FIXTURES = Path(__file__).resolve().parents[2] / "shared" / "fixtures"


def test_shared_fixtures_follow_contract() -> None:
    for path in FIXTURES.glob("*.json"):
        PerceptionResult.model_validate(json.loads(path.read_text(encoding="utf-8")))

