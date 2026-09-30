"""API 요청·응답 스키마. docs/04-api-schema.md 3~4장 기준. 문서와 다르면 문서가 우선."""
from pydantic import BaseModel, Field

from .state import (
    AttitudeFeedback,
    FitFeedback,
    QuestionFeedback,
    QuestionType,
    SessionStatus,
    Step,
)


class ErrorBody(BaseModel):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(BaseModel):
    """오류 형식: {"error": {"code": "...", "message": "..."}}"""

    error: ErrorBody


# 04 문서 4장 오류 코드: (HTTP, code)
ERROR_CODES = {
    "TEXT_EXTRACTION_FAILED": 422,
    "MISSING_REQUIRED_DOC": 422,
    "CONSENT_REQUIRED": 422,
    "SESSION_NOT_FOUND": 404,
    "NOT_IN_PROGRESS": 409,
    "UNKNOWN_QUESTION": 422,
    "NOT_READY": 409,
}


class CreateInterviewResponse(BaseModel):  # 201
    session_id: str
    status: SessionStatus


class PublicQuestion(BaseModel):
    """면접 중 노출용. 기대 요소·평가 기준·연결 정보 없음."""

    question_id: str
    order: int
    type: QuestionType
    text: str


class InterviewStatusResponse(BaseModel):  # GET /api/interviews/{id}, 200
    session_id: str
    status: SessionStatus
    steps: list[Step] = []
    questions: list[PublicQuestion] | None = None  # READY 이후 5개
    error: str | None = None  # FAILED일 때 (04 문서 8장 3번, 형식 미정)


class SubmitAnswerResponse(BaseModel):  # POST /answers, 202
    question_id: str
    received: bool
    next_question_id: str | None
    status: SessionStatus


class ReportQuestion(BaseModel):
    question_id: str
    type: QuestionType
    text: str
    answer_text: str | None = None  # NO_SPEECH·FAILED면 null


class ReportClaim(BaseModel):
    claim_id: str
    text: str


class ReportCheckpoint(BaseModel):
    checkpoint_id: str
    title: str


class ReportResponse(BaseModel):  # GET /report, 200
    session_id: str
    attitude: AttitudeFeedback
    job_fit: FitFeedback
    consistency: FitFeedback
    per_question: list[QuestionFeedback] = []
    questions: list[ReportQuestion] = []
    claims: list[ReportClaim] = []
    checkpoints: list[ReportCheckpoint] = []


class DeliveryMetricsInput(BaseModel):
    """POST /answers의 delivery_metrics(JSON 문자열) 내용."""

    measurable: bool
    frontal_ratio: float | None = Field(default=None, ge=0, le=1)
    gaze_away_count: int | None = None
