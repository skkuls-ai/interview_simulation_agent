"""Generate technical interview questions from analyzed candidate experiences."""

from __future__ import annotations

import json
from collections.abc import Sequence

from ..llm.client import JsonLLM
from ..validators.technical_question_validator import (
    TECHNICAL_QUESTION_COUNT,
    TechnicalQuestionGeneration,
    TechnicalQuestionSet,
    TechnicalQuestionValidationError,
    validate_technical_question_generation,
)
from .blueprint import Experience, JDRequirement

QUESTION_COUNT = TECHNICAL_QUESTION_COUNT

SYSTEM = """\
당신은 지원자의 기술 경험을 확인하는 면접 질문 생성 에이전트입니다.
입력으로 주어진 분석 결과만 사용하고, 거기에 없는 기술·성과·역할을 지원자가 했다고 가정하지 않습니다.

규칙:
1. 지원자의 프로젝트에서 실제로 사용한 기술, 설계, 구현, 데이터 처리, 문제 해결을 구체적으로 확인합니다.
2. 지원자 경험과 직접 연결된 서로 다른 기술 질문을 정확히 2개 만듭니다.
3. 각 질문은 한 번에 하나의 핵심만 묻고, 존댓말로 작성하며, 답을 유도하지 않습니다.
4. 각 질문은 최소 하나의 입력 experience ID를 근거로 지정합니다. JD와 연결되면 requirement ID도 지정합니다.
5. 각 질문에 좋은 답변에서 확인할 수 있는 평가 기준을 2~4개 작성합니다.
6. 경험 정보가 기술 질문 2개를 뒷받침하기에 부족하면 status=insufficient_analysis, questions=[]로 반환하고 이유를 씁니다.
7. 나이, 출신, 가족, 혼인, 종교 등 직무와 무관하거나 차별적인 질문은 만들지 않습니다.
"""


def _analysis_prompt(
    target_role: str | None,
    experiences: Sequence[Experience],
    requirements: Sequence[JDRequirement],
) -> str:
    return "\n".join([
        "## 지원 직무",
        target_role or "입력된 직무명 없음",
        "## 분석된 경험",
        json.dumps([experience.model_dump(mode="json") for experience in experiences], ensure_ascii=False, indent=2),
        "## 직무 요구사항",
        json.dumps([requirement.model_dump(mode="json") for requirement in requirements], ensure_ascii=False, indent=2),
        f"기술 질문 {QUESTION_COUNT}개를 생성하거나, 근거가 부족하면 insufficient_analysis를 반환하세요.",
    ])


class TechnicalQuestionAgent:
    """Create a validated, source-linked set of two technical interview questions."""

    def __init__(self, llm: JsonLLM):
        self.llm = llm

    def generate(
        self,
        experiences: Sequence[Experience],
        requirements: Sequence[JDRequirement] = (),
        target_role: str | None = None,
    ) -> TechnicalQuestionSet:
        usable_experiences = [
            experience for experience in experiences
            if experience.title.strip() or experience.summary.strip() or experience.claimed_results
        ]
        if not usable_experiences:
            return TechnicalQuestionSet(
                status="insufficient_analysis",
                reason="기술 경험 분석 결과가 없어 지원자 맞춤 질문을 만들 수 없습니다.",
                questions=[],
            )

        experience_ids = [experience.id for experience in usable_experiences]
        if len(experience_ids) != len(set(experience_ids)):
            raise TechnicalQuestionValidationError("분석 결과의 experience ID가 중복되었습니다.")
        requirement_ids = [requirement.id for requirement in requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise TechnicalQuestionValidationError("분석 결과의 requirement ID가 중복되었습니다.")

        generation, _ = self.llm.generate_json(
            "analysis", SYSTEM, _analysis_prompt(target_role, usable_experiences, requirements),
            TechnicalQuestionGeneration,
        )
        return validate_technical_question_generation(generation, usable_experiences, list(requirements))