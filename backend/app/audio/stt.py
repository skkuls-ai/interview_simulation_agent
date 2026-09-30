"""녹음 수신 후 변환(STT)하고 음성 파일을 삭제한다 (F-008).
STT 제공사는 미정이므로 SttProvider 프로토콜만 두고 stub을 쓴다."""
import os
from typing import Protocol

from ..schemas.state import TranscriptStatus
from ..store import Store


class SttProvider(Protocol):
    def transcribe(self, path: str) -> str | None:
        """변환 텍스트. 무음이면 None 또는 빈 문자열."""


class StubStt:
    def transcribe(self, path: str) -> str | None:
        return "테스트 답변입니다."


def get_stt() -> SttProvider:
    # TODO: 제공사 확정 후 실제 구현으로 교체
    return StubStt()


def transcribe_and_delete(store: Store, session_id: str, question_id: str,
                          path: str | None, stt: SttProvider | None = None) -> None:
    """변환 결과를 Answer에 기록하고, 성공·실패와 상관없이 음성 파일을 지운다."""
    text: str | None = None
    status = TranscriptStatus.NO_SPEECH
    try:
        if path:
            text = (stt or get_stt()).transcribe(path)
            status = TranscriptStatus.DONE if text and text.strip() else TranscriptStatus.NO_SPEECH
    except Exception:
        status = TranscriptStatus.FAILED
        text = None
    finally:
        if path and os.path.exists(path):
            os.remove(path)

    record = store.get(session_id)
    if record is None:
        return
    with store.lock:
        for answer in record.state.answers:
            if answer.question_id == question_id:
                answer.transcript = text if status == TranscriptStatus.DONE else None
                answer.transcript_status = status
