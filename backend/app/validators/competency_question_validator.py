"""Validate selected competency questions and convert them to API questions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.banks.competency_question_bank import CompetencyQuestionBank
from app.schemas.state import Analysis, Question, QuestionType

QUESTION_COUNT = 2
ALLOWED_TYPES = {"경험면접", "상황면접"}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompetencySelectionDraft(_Model):
    question_number: int = Field(ge=1)
    requirement_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)


class CompetencyQuestionGeneration(_Model):
    status: Literal["ready", "insufficient_analysis"]
    reason: str
    selections: list[CompetencySelectionDraft]


class CompetencyQuestionValidationResult(_Model):
    is_valid: bool
    status: Literal["ready", "insufficient_analysis"]
    reason: str
    questions: list[Question]
    selection_reasons: list[str] = Field(default_factory=list)


class CompetencyQuestionValidationError(ValueError):
    """Raised when generated selections fail the question-bank contract."""


def validate_competency_question_selection(
    generation: CompetencyQuestionGeneration,
    analysis: Analysis,
    bank: CompetencyQuestionBank,
) -> CompetencyQuestionValidationResult:
    def invalid(reason: str) -> CompetencyQuestionValidationResult:
        return CompetencyQuestionValidationResult(
            is_valid=False, status=generation.status, reason=reason, questions=[],
        )

    if generation.status == "insufficient_analysis":
        if generation.selections:
            return invalid("분석 부족 결과에는 선택 질문이 없어야 합니다.")
        return CompetencyQuestionValidationResult(
            is_valid=True, status=generation.status, reason=generation.reason, questions=[],
        )

    if len(generation.selections) != QUESTION_COUNT:
        return invalid(f"역량 질문은 정확히 {QUESTION_COUNT}개여야 합니다.")

    requirement_ids = {requirement.requirement_id for requirement in analysis.requirements}
    numbers: set[int] = set()
    competencies: set[str] = set()
    questions: list[Question] = []
    reasons: list[str] = []

    for index, selection in enumerate(generation.selections, start=2):
        if selection.question_number in numbers:
            return invalid("같은 질문을 중복 선택했습니다.")
        numbers.add(selection.question_number)

        bank_question = bank.by_number(selection.question_number)
        if bank_question is None:
            return invalid(f"질문 은행에 없는 번호입니다: {selection.question_number}")
        if bank_question.question_type not in ALLOWED_TYPES:
            return invalid(f"인성·역량 질문 유형이 아닙니다: {selection.question_number}")
        if bank_question.competency in competencies:
            return invalid("서로 다른 역량을 확인하는 질문을 선택해야 합니다.")
        competencies.add(bank_question.competency)

        selected_requirements = set(selection.requirement_ids)
        if len(selected_requirements) != len(selection.requirement_ids):
            return invalid("requirement_id가 중복되었습니다.")
        if not selected_requirements <= requirement_ids:
            return invalid("분석 결과에 없는 requirement_id를 참조했습니다.")

        criteria = [*(f"질문 의도: {intent}" for intent in bank_question.intents)]
        criteria.extend(f"Positive: {item}" for item in bank_question.positive_checkpoints)
        criteria.extend(f"Negative: {item}" for item in bank_question.negative_checkpoints)
        questions.append(Question(
            question_id=f"Q-{index}",
            order=index,
            type=QuestionType.BEHAVIOR,
            text=bank_question.text,
            question_bank_id=bank_question.question_bank_id,
            criteria=criteria,
        ))
        reasons.append(selection.rationale)

    return CompetencyQuestionValidationResult(
        is_valid=True,
        status=generation.status,
        reason=generation.reason,
        questions=questions,
        selection_reasons=reasons,
    )