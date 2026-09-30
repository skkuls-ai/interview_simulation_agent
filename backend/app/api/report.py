from fastapi import APIRouter

from ..errors import ApiError
from ..schemas.api import ReportResponse
from ..schemas.state import SessionStatus
from ..store import store

router = APIRouter(prefix="/api/interviews")


@router.get("/{session_id}/report", response_model=ReportResponse)
def get_report(session_id: str):
    record = store.get(session_id)
    if record is None:
        raise ApiError("SESSION_NOT_FOUND", "세션을 찾을 수 없습니다")
    if record.state.status != SessionStatus.COMPLETED or record.report_response is None:
        raise ApiError("NOT_READY", "피드백이 아직 준비되지 않았습니다")
    return record.report_response
