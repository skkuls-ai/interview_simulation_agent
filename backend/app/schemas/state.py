"""세션 State 스키마. docs/04-api-schema.md 6장(ERD)·7장(ID 규칙) 기준. 문서와 다르면 문서가 우선."""
from enum import Enum

from pydantic import BaseModel, Field

# ID 형식 (04 문서 7장)
SESSION_ID = r"^S-[0-9a-f]{8}$"
REQUIREMENT_ID = r"^RQ-\d{3}$"
CLAIM_ID = r"^CL-\d{3}$"
CHECKPOINT_ID = r"^CP-\d{3}$"
QUESTION_ID = r"^Q-[1-5]$"
QUOTE_ID = r"^QT-\d{3}$"


class SessionStatus(str, Enum):
    PREPARING = "PREPARING"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class StepState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"


class QuestionType(str, Enum):
    INTRO = "INTRO"
    BEHAVIOR = "BEHAVIOR"
    TECH = "TECH"


class SourceDoc(str, Enum):
    RESUME = "resume"
    COVER_LETTER = "cover_letter"
    JOB_POSTING = "job_posting"
    JOB_DESCRIPTION = "job_description"


class RequirementKind(str, Enum):
    SKILL = "SKILL"
    DUTY = "DUTY"
    TALENT = "TALENT"


class ClaimType(str, Enum):
    METRIC = "METRIC"
    ROLE = "ROLE"
    TECH = "TECH"
    PROBLEM = "PROBLEM"
    DECISION = "DECISION"
    COLLAB = "COLLAB"
    MEASURE = "MEASURE"


class TranscriptStatus(str, Enum):
    PENDING = "PENDING"
    DONE = "DONE"
    NO_SPEECH = "NO_SPEECH"
    FAILED = "FAILED"


class Verdict(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    NEEDS_WORK = "NEEDS_WORK"
    INSUFFICIENT = "INSUFFICIENT"
    WITHHELD = "WITHHELD"


class Step(BaseModel):
    step_id: str
    label: str
    state: StepState
    detail: str | None = None


class Requirement(BaseModel):
    requirement_id: str = Field(pattern=REQUIREMENT_ID)
    text: str
    source_doc: SourceDoc
    kind: RequirementKind


class RequirementLink(BaseModel):
    requirement_id: str = Field(pattern=REQUIREMENT_ID)
    claim_ids: list[str] = []  # 비어 있으면 서류에 근거 없음


class Claim(BaseModel):
    claim_id: str = Field(pattern=CLAIM_ID)
    source_doc: SourceDoc
    text: str  # 원문 그대로
    types: list[ClaimType] = []


class Checkpoint(BaseModel):
    checkpoint_id: str = Field(pattern=CHECKPOINT_ID)
    claim_ids: list[str] = []
    title: str
    what_to_verify: str


class Analysis(BaseModel):
    requirements: list[Requirement] = []
    claims: list[Claim] = []
    checkpoints: list[Checkpoint] = []
    links: list[RequirementLink] = []


class Question(BaseModel):
    question_id: str = Field(pattern=QUESTION_ID)
    order: int
    type: QuestionType
    text: str
    checkpoint_ids: list[str] = []
    question_bank_id: str | None = None  # TECH·BEHAVIOR 필수
    criteria: list[str] = []  # 면접 중 API에 노출 금지


class DeliveryMetrics(BaseModel):
    measurable: bool
    frontal_ratio: float | None = Field(default=None, ge=0, le=1)
    gaze_away_count: int | None = None


class Answer(BaseModel):
    question_id: str = Field(pattern=QUESTION_ID)
    transcript: str | None = None
    transcript_status: TranscriptStatus = TranscriptStatus.PENDING
    duration_sec: float
    timed_out: bool = False
    words_per_min: float | None = None
    filler_count: int | None = None
    delivery: DeliveryMetrics | None = None


class Quote(BaseModel):
    quote_id: str = Field(pattern=QUOTE_ID)
    question_id: str = Field(pattern=QUESTION_ID)
    text: str  # transcript 안의 문장만
    start: int | None = None
    end: int | None = None


class AttitudeFeedback(BaseModel):
    metrics: dict  # speech, gaze, time
    advice: list[str] = []
    quotes: list[Quote] = []  # 판정·점수 없음


class FitFeedback(BaseModel):
    verdict: Verdict
    reason: str
    quotes: list[Quote] = []
    refs: list[str] = []  # RQ- 또는 CL- ID


class QuestionFeedback(BaseModel):
    question_id: str = Field(pattern=QUESTION_ID)
    strengths: list[str] = []
    gaps: list[str] = []
    next_action: str
    linked_claim_ids: list[str] = []
    linked_checkpoint_ids: list[str] = []


class Report(BaseModel):
    attitude: AttitudeFeedback
    job_fit: FitFeedback
    consistency: FitFeedback
    per_question: list[QuestionFeedback] = []


class InterviewState(BaseModel):
    """메모리 저장소(store.py)가 세션마다 들고 있는 State."""

    session_id: str = Field(pattern=SESSION_ID)
    status: SessionStatus = SessionStatus.PREPARING
    resume_text: str
    job_posting_text: str  # 인재상 포함
    job_description_text: str
    cover_letter_text: str
    consent_at: str  # ISO-8601
    steps: list[Step] = []
    analysis: Analysis = Analysis()
    questions: list[Question] = []
    answers: list[Answer] = []
    report: Report | None = None
    error: str | None = None
