"""Graph node that selects two job-relevant competency questions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, TypedDict

from app.llm.client import JsonLLM
from app.llm.competency_question_agent import CompetencyQuestionAgent
from app.schemas.state import Analysis, Question
from app.validators.competency_question_validator import CompetencyQuestionValidationResult


class CompetencyQuestionNodeState(TypedDict, total=False):
    analysis: Analysis
    competency_question_status: Literal["ready", "insufficient_analysis"]
    competency_question_reason: str
    competency_questions: list[Question]
    competency_question_reasons: list[str]


def build_competency_question_node(
    llm: JsonLLM,
) -> Callable[[CompetencyQuestionNodeState], dict]:
    agent = CompetencyQuestionAgent(llm)

    def competency_questions_node(state: CompetencyQuestionNodeState) -> dict:
        result: CompetencyQuestionValidationResult = agent.generate(state["analysis"])
        return {
            "competency_question_status": result.status,
            "competency_question_reason": result.reason,
            "competency_questions": result.questions,
            "competency_question_reasons": result.selection_reasons,
        }

    return competency_questions_node