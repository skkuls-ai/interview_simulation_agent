from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from .schemas import PerceptionResult, VisualMetrics
from .service import PerceptionService
from .stt import GeminiSTTService


router = APIRouter(prefix="/api/perception", tags=["perception"])
service = PerceptionService(GeminiSTTService())
MAX_AUDIO_BYTES = 10 * 1024 * 1024


def parse_visual_metrics(value: str | None) -> VisualMetrics | None:
    if value is None or not value.strip():
        return None
    try:
        return VisualMetrics.model_validate_json(value)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="visual_metrics 형식이 올바르지 않습니다.") from exc


@router.post("/analyze", response_model=PerceptionResult)
async def analyze_perception(
    session_id: str = Form(...),
    question_id: str = Form(...),
    answer_id: str = Form(...),
    duration_seconds: float = Form(..., ge=0),
    visual_metrics: str | None = Form(None),
    audio: UploadFile = File(...),
) -> PerceptionResult:
    if not (audio.content_type or "").startswith("audio/"):
        raise HTTPException(status_code=415, detail="오디오 파일만 업로드할 수 있습니다.")

    audio_bytes = await audio.read(MAX_AUDIO_BYTES + 1)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="오디오 파일이 비어 있습니다.")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="오디오 파일은 10MB 이하여야 합니다.")

    return await service.analyze(
        session_id=session_id,
        question_id=question_id,
        answer_id=answer_id,
        audio=audio_bytes,
        mime_type=audio.content_type or "audio/webm",
        duration_seconds=duration_seconds,
        visual_metrics=parse_visual_metrics(visual_metrics),
    )
