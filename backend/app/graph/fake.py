"""가짜 진행기. 진짜 준비·평가 그래프는 W-20에서 이 두 함수를 교체한다.
shared/mock의 JSON을 지연을 두고 순서대로 State에 채워 화면·API 한 바퀴를 확인할 수 있게 한다."""
import os
import time

from ..schemas.api import ReportResponse
from ..schemas.state import Question, SessionStatus, Step
from ..store import Store
from .mock_data import load


_load = load


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
