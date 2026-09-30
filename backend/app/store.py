"""세션 State 메모리 저장소. 세션은 메모리에 두며 서버 재시작 시 사라져도 된다(07 규칙).
워커가 여러 개면 세션이 갈라지므로 uvicorn 워커는 1개로 고정한다."""
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .schemas.api import ReportResponse, SubmitAnswerResponse
from .schemas.state import InterviewState


@dataclass
class SessionRecord:
    state: InterviewState
    # 같은 question_id 재전송 시 이전 응답을 그대로 돌려주기 위한 기록
    answer_responses: dict[str, SubmitAnswerResponse] = field(default_factory=dict)
    # GET /report 응답 (state.report에 questions·claims·checkpoints를 더한 모양)
    report_response: ReportResponse | None = None


class Store:
    def __init__(self) -> None:
        self._records: dict[str, SessionRecord] = {}
        self.lock = threading.RLock()

    def create(self, *, resume_text: str, job_posting_text: str,
               job_description_text: str, cover_letter_text: str) -> SessionRecord:
        with self.lock:
            sid = f"S-{uuid.uuid4().hex[:8]}"
            state = InterviewState(
                session_id=sid,
                resume_text=resume_text,
                job_posting_text=job_posting_text,
                job_description_text=job_description_text,
                cover_letter_text=cover_letter_text,
                consent_at=datetime.now(timezone.utc).isoformat(),
            )
            record = SessionRecord(state=state)
            self._records[sid] = record
            return record

    def get(self, session_id: str) -> SessionRecord | None:
        with self.lock:
            return self._records.get(session_id)


store = Store()
