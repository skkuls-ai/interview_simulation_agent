"""Graph node that generates and validates technical interview questions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, TypedDict

from app.llm.client import JsonLLM
from app.llm.technical_question_agent import TechnicalQuestionAgent
from app.schemas.state import Analysis, Question


class TechnicalQuestionNodeState(TypedDict, total=False):
    analysis: Analysis
    technical_question_status: Literal["ready", "insufficient_analysis"]
    technical_question_reason: str
    technical_questions: list[Question]


def build_technical_question_node(
    llm: JsonLLM,
) -> Callable[[TechnicalQuestionNodeState], dict]:
    agent = TechnicalQuestionAgent(llm)

    def technical_questions_node(state: TechnicalQuestionNodeState) -> dict:
        result = agent.generate(state["analysis"])
        return {
            "technical_question_status": result.status,
            "technical_question_reason": result.reason,
            "technical_questions": result.questions,
        }

    return technical_questions_node