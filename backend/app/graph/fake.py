"""가짜 진행기. 진짜 준비·평가 그래프는 W-20에서 이 두 함수를 교체한다.
shared/mock의 JSON을 지연을 두고 순서대로 State에 채워 화면·API 한 바퀴를 확인할 수 있게 한다."""
import json
import os
import time
from pathlib import Path

from ..schemas.api import ReportResponse
from ..schemas.state import Question, SessionStatus, Step
from ..store import Store


def _mock_dir() -> Path:
    if os.environ.get("MOCK_DIR"):
        return Path(os.environ["MOCK_DIR"])
    here = Path(__file__).resolve()
    # 저장소: backend/app/graph/ → parents[3]가 루트, Docker: /srv/app/graph/ → parents[2]가 /srv
    for base in (here.parents[3], here.parents[2]):
        if (base / "shared" / "mock").is_dir():
            return base / "shared" / "mock"
    raise FileNotFoundError("shared/mock 폴더를 찾을 수 없다 (MOCK_DIR로 지정 가능)")


def _load(name: str) -> dict:
    return json.loads((_mock_dir() / name).read_text(encoding="utf-8"))


def _delay() -> float:
    return float(os.environ.get("FAKE_GRAPH_DELAY_SEC", "1.0"))


def run_prepare(store: Store, session_id: str) -> None:
    record = store.get(session_id)
    if record is None:
        return
    with store.lock:
        record.state.steps = [Step(**s) for s in _load("session_preparing.json")["steps"]]
    time.sleep(_delay())
    ready = _load("session_ready.json")
    with store.lock:
        record.state.steps = [Step(**s) for s in ready["steps"]]
        record.state.questions = [Question(**q) for q in ready["questions"]]
        record.state.status = SessionStatus.READY


def run_evaluate(store: Store, session_id: str) -> None:
    record = store.get(session_id)
    if record is None:
        return
    with store.lock:
        record.state.steps = [Step(**s) for s in _load("session_evaluating.json")["steps"]]
    time.sleep(_delay())
    report = _load("report.json")
    report["session_id"] = session_id
    with store.lock:
        record.report_response = ReportResponse.model_validate(report)
        record.state.status = SessionStatus.COMPLETED
