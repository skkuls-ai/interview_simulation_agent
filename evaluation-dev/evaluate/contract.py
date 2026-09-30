"""docs/04 계약 모델 임시 복사본 (E 가 읽고 쓰는 부분만).

C 의 schemas/state.py 가 올라오면 이 파일을 지우고 import 를 그쪽으로 바꾼다.
필드 이름과 값은 「개발 계약·담당표」 2절 State 를 그대로 따른다.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

# ---------------------------------------------------------------- 준비 단계 (A, B 가 채움, E 는 읽기만)


class Requirement(BaseModel):
    requirement_id: str
    text: str
    source_doc: Literal["job_posting", "job_description"]
    kind: Literal["SKILL", "DUTY", "TALENT"]


class Claim(BaseModel):
    claim_id: str
    source_doc: Literal["resume", "cover_letter"]
    text: str
    types: list[Literal["METRIC", "ROLE", "TECH", "PROBLEM", "DECISION", "COLLAB", "MEASURE"]] = []


class Checkpoint(BaseModel):
    checkpoint_id: str
    claim_ids: list[str]
    title: str
    what_to_verify: str = ""


class RequirementLink(BaseModel):
    requirement_id: str
    claim_ids: list[str]


class Analysis(BaseModel):
    requirements: list[Requirement]
    claims: list[Claim]
    checkpoints: list[Checkpoint]
    links: list[RequirementLink] = []


class Question(BaseModel):
    question_id: str
    order: int
    type: Literal["INTRO", "BEHAVIOR", "TECH"]
    text: str
    checkpoint_ids: list[str] = []
    question_bank_id: Optional[str] = None
    criteria: list[str] = []


# ---------------------------------------------------------------- 면접 단계 (C 가 채움)


class DeliveryMetrics(BaseModel):  # 프런트가 계산해 보냄 (D), 점수 미반영
    measurable: bool
    frontal_ratio: Optional[float] = None  # 0~1, 정면 유지 비율
    gaze_away_count: Optional[int] = None


class Answer(BaseModel):
    question_id: str
    transcript: Optional[str] = None
    transcript_status: Literal["PENDING", "DONE", "NO_SPEECH", "FAILED"] = "PENDING"
    duration_sec: float
    timed_out: bool
    delivery: Optional[DeliveryMetrics] = None
    words_per_min: Optional[float] = None  # 코드가 transcript 에서 계산 (Should)
    filler_count: Optional[int] = None  # 코드가 transcript 에서 계산 (Should)


# ---------------------------------------------------------------- 피드백 (E 가 채움)

Verdict = Literal["SUFFICIENT", "NEEDS_WORK", "INSUFFICIENT", "WITHHELD"]


class Quote(BaseModel):
    quote_id: str
    question_id: str
    text: str
    start: Optional[int] = None
    end: Optional[int] = None


class FitFeedback(BaseModel):  # 직무 적합성, 답변 일관성 공통
    verdict: Verdict
    reason: str
    quotes: list[Quote]
    refs: list[str]


class AttitudeFeedback(BaseModel):
    metrics: dict
    advice: list[str]
    quotes: list[Quote] = []


class QuestionFeedback(BaseModel):
    question_id: str
    strengths: list[str]
    gaps: list[str]
    next_action: str
    linked_claim_ids: list[str] = []
    linked_checkpoint_ids: list[str] = []


class Report(BaseModel):
    attitude: AttitudeFeedback
    job_fit: FitFeedback
    consistency: FitFeedback
    per_question: list[QuestionFeedback]
