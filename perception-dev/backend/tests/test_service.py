import asyncio

from fastapi import HTTPException

from app.perception.routes import parse_visual_metrics
from app.perception.schemas import VisualMetrics
from app.perception.service import PerceptionService


class SuccessfulSTT:
    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        assert audio
        assert mime_type == "audio/webm"
        return "프로젝트에서 API 서버를 구현했습니다."


class FailingSTT:
    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        raise RuntimeError("provider unavailable")


def test_service_combines_audio_and_visual_results() -> None:
    visual = VisualMetrics(
        face_detection_ratio=0.9,
        camera_gaze_ratio=0.8,
        expression_variance=0.02,
    )
    result = asyncio.run(
        PerceptionService(SuccessfulSTT()).analyze(
            session_id="s",
            question_id="q",
            answer_id="a",
            audio=b"audio",
            mime_type="audio/webm",
            duration_seconds=30,
            visual_metrics=visual,
        )
    )

    assert result.transcript.text == "프로젝트에서 API 서버를 구현했습니다."
    assert result.quality.audio_available is True
    assert result.quality.visual_available is True
    assert result.warnings == []


def test_stt_provider_failure_returns_degraded_result() -> None:
    result = asyncio.run(
        PerceptionService(FailingSTT()).analyze(
            session_id="s",
            question_id="q",
            answer_id="a",
            audio=b"audio",
            mime_type="audio/webm",
            duration_seconds=30,
            visual_metrics=None,
        )
    )

    assert result.transcript.text == ""
    assert result.quality.audio_available is False
    assert set(result.warnings) == {"stt_failed", "visual_unavailable"}


def test_invalid_visual_metrics_is_rejected() -> None:
    try:
        parse_visual_metrics('{"face_detection_ratio": 2}')
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("잘못된 visual_metrics가 허용되었습니다.")
