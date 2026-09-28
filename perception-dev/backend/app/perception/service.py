from __future__ import annotations

import logging

from .audio_analyzer import analyze_audio_text
from .schemas import PerceptionQuality, PerceptionResult, TranscriptResult, VisualMetrics
from .stt import STTService


logger = logging.getLogger(__name__)


class PerceptionService:
    def __init__(self, stt_service: STTService) -> None:
        self.stt_service = stt_service

    async def analyze(
        self,
        *,
        session_id: str,
        question_id: str,
        answer_id: str,
        audio: bytes,
        mime_type: str,
        duration_seconds: float,
        visual_metrics: VisualMetrics | None,
    ) -> PerceptionResult:
        warnings: list[str] = []
        try:
            transcript = await self.stt_service.transcribe(audio, mime_type)
        except Exception:
            logger.exception("STT 변환에 실패했습니다.")
            transcript = ""
            warnings.append("stt_failed")
        audio_metrics = analyze_audio_text(transcript, duration_seconds)

        visual = visual_metrics
        if visual is None:
            warnings.append("visual_unavailable")

        if not transcript.strip() and "stt_failed" not in warnings:
            warnings.append("stt_failed")

        return PerceptionResult(
            session_id=session_id,
            question_id=question_id,
            answer_id=answer_id,
            transcript=TranscriptResult(text=transcript, duration_seconds=duration_seconds),
            audio=audio_metrics,
            visual=visual,
            quality=PerceptionQuality(
                audio_available=bool(transcript.strip()),
                visual_available=visual is not None,
            ),
            warnings=warnings,
        )
