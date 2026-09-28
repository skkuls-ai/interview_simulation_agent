from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TranscriptResult(BaseModel):
    text: str
    duration_seconds: float = Field(ge=0)


class AudioMetrics(BaseModel):
    eojeol_count: int = Field(ge=0)
    speech_rate: float = Field(ge=0)


class VisualMetrics(BaseModel):
    face_detection_ratio: float = Field(ge=0, le=1)
    camera_gaze_ratio: float = Field(ge=0, le=1)
    expression_variance: float = Field(ge=0)


class PerceptionQuality(BaseModel):
    audio_available: bool
    visual_available: bool


class PerceptionResult(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    session_id: str
    question_id: str
    answer_id: str
    transcript: TranscriptResult
    audio: AudioMetrics
    visual: VisualMetrics | None
    quality: PerceptionQuality
    warnings: list[str] = Field(default_factory=list)
