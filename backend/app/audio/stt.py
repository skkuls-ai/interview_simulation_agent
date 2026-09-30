"""녹음 수신 후 변환(STT)하고 음성 파일을 삭제한다 (F-008).

STT_MODE: auto(기본) | gemini | stub
- auto: GOOGLE_CLOUD_PROJECT 또는 GEMINI_API_KEY가 있으면 gemini, 없으면 stub
- gemini: Gemini 오디오 입력으로 변환 (audio/gemini_stt.py)
- stub: 고정 텍스트 (테스트, 키 없는 Docker)
"""
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


def stt_mode() -> str:
    mode = os.environ.get("STT_MODE", "auto").strip().lower()
    if mode in ("gemini", "stub"):
        return mode
    from ..llm.settings import LLMSettings

    settings = LLMSettings.from_env()  # 저장소 루트 .env도 읽는다
    return "gemini" if (settings.project or settings.api_key) else "stub"


_gemini: SttProvider | None = None


def get_stt() -> SttProvider:
    global _gemini
    if stt_mode() == "stub":
        return StubStt()
    if _gemini is None:
        from .gemini_stt import GeminiStt

        _gemini = GeminiStt()
    return _gemini


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
