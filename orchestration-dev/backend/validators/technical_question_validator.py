"""Validate generated technical questions against their analysis inputs."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..interview.blueprint import Experience, JDRequirement
from ..interview.guards import check_generated

TECHNICAL_QUESTION_COUNT = 2


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TechnicalQuestionDraft(_Model):
    text: str = Field(min_length=10, max_length=120)
    experience_ids: list[str] = Field(min_length=1)
    requirement_ids: list[str] = Field(default_factory=list)
    evaluation_criteria: list[str] = Field(min_length=1, max_length=4)


class TechnicalQuestionGeneration(_Model):
    status: Literal["ready", "insufficient_analysis"]
    reason: str
    questions: list[TechnicalQuestionDraft]


class TechnicalQuestion(_Model):
    question_id: str = Field(pattern=r"^TQ-\d{3}$")
    text: str
    experience_ids: list[str]
    requirement_ids: list[str]
    evaluation_criteria: list[str]


class TechnicalQuestionSet(_Model):
    status: Literal["ready", "insufficient_analysis"]
    reason: str
    questions: list[TechnicalQuestion]


class TechnicalQuestionValidationError(ValueError):
    """The generated questions do not satisfy the technical-question contract."""


def validate_technical_question_generation(
    generation: TechnicalQuestionGeneration,
    experiences: list[Experience],
    requirements: list[JDRequirement],
) -> TechnicalQuestionSet:
    if generation.status == "insufficient_analysis":
        if generation.questions:
            raise TechnicalQuestionValidationError("insufficient_analysis 결과에는 질문이 없어야 합니다.")
        return TechnicalQuestionSet(status=generation.status, reason=generation.reason, questions=[])

    if len(generation.questions) != TECHNICAL_QUESTION_COUNT:
        raise TechnicalQuestionValidationError(f"질문은 정확히 {TECHNICAL_QUESTION_COUNT}개여야 합니다.")

    experience_ids = {experience.id for experience in experiences}
    requirement_ids = {requirement.id for requirement in requirements}
    seen_texts: set[str] = set()
    validated: list[TechnicalQuestion] = []
    for question in generation.questions:
        normalized_text = re.sub(r"\s+", "", question.text).casefold()
        if normalized_text in seen_texts:
            raise TechnicalQuestionValidationError("중복 질문이 있습니다.")
        seen_texts.add(normalized_text)

        if not set(question.experience_ids) <= experience_ids:
            raise TechnicalQuestionValidationError("입력에 없는 experience ID를 참조했습니다.")
        if not set(question.requirement_ids) <= requirement_ids:
            raise TechnicalQuestionValidationError("입력에 없는 requirement ID를 참조했습니다.")
        if len(question.experience_ids) != len(set(question.experience_ids)):
            raise TechnicalQuestionValidationError("experience ID가 중복되었습니다.")
        if len(question.requirement_ids) != len(set(question.requirement_ids)):
            raise TechnicalQuestionValidationError("requirement ID가 중복되었습니다.")
        if problem := check_generated(question.text):
            raise TechnicalQuestionValidationError(f"질문 안전 검사 실패: {problem}")

        validated.append(TechnicalQuestion(
            question_id=f"TQ-{len(validated) + 1:03d}",
            **question.model_dump(),
        ))

    return TechnicalQuestionSet(status=generation.status, reason=generation.reason, questions=validated)