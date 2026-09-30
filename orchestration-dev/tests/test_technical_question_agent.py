from __future__ import annotations

import pytest

from backend.interview.blueprint import Experience, JDRequirement
from backend.interview.technical_question_agent import (
    TechnicalQuestionAgent,
)
from backend.llm.client import CallInfo
from backend.validators.technical_question_validator import (
    TechnicalQuestionGeneration,
    TechnicalQuestionValidationError,
    validate_technical_question_generation,
)


EXPERIENCES = [
    Experience(
        id="E1", source="resume", title="채용 데이터 대시보드",
        summary="Python과 SQL로 채용 퍼널 데이터를 집계하는 대시보드를 구축했습니다.",
        claimed_results=["월간 리포트 작성 시간을 줄였습니다."],
    ),
    Experience(
        id="E2", source="resume", title="지원자 이탈 분석",
        summary="단계별 전환 데이터를 분석해 지원자 이탈 원인을 찾았습니다.",
    ),
]
REQUIREMENTS = [JDRequirement(
    id="R1", text="채용 데이터 분석 및 프로세스 개선", kind="skill", importance="must",
)]


def valid_output(**updates):
    output = {
        "status": "ready",
        "reason": "두 경험에서 서로 다른 기술 주제를 확인할 수 있습니다.",
        "questions": [
            {
                "text": "대시보드에서 채용 퍼널 데이터를 어떤 기준으로 집계하고 검증하셨나요?",
                "experience_ids": ["E1"],
                "requirement_ids": ["R1"],
                "evaluation_criteria": ["지표 정의", "데이터 검증"],
            },
            {
                "text": "지원자 이탈 원인을 찾을 때 어떤 분석 방법과 변수를 사용하셨나요?",
                "experience_ids": ["E2"],
                "requirement_ids": ["R1"],
                "evaluation_criteria": ["분석 방법 선택 근거", "결과 해석"],
            },
        ],
    }
    output.update(updates)
    return output


class FakeLLM:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def generate_json(self, role, system, prompt, schema):
        self.calls.append((role, system, prompt, schema))
        return schema.model_validate(self.output), CallInfo(
            role=role, model="fake", latency_sec=0.01, attempts=1,
        )


def test_generates_two_questions_with_code_issued_ids_and_analysis_refs():
    llm = FakeLLM(valid_output())

    result = TechnicalQuestionAgent(llm).generate(EXPERIENCES, REQUIREMENTS, target_role="데이터 엔지니어")

    assert llm.calls[0][0] == "analysis"
    assert "E1" in llm.calls[0][2] and "R1" in llm.calls[0][2]
    assert result.status == "ready"
    assert [question.question_id for question in result.questions] == ["TQ-001", "TQ-002"]
    assert result.questions[0].experience_ids == ["E1"]
    assert result.questions[0].evaluation_criteria


def test_empty_analysis_returns_insufficient_without_calling_llm():
    llm = FakeLLM(valid_output())

    result = TechnicalQuestionAgent(llm).generate([])

    assert result.status == "insufficient_analysis"
    assert result.questions == []
    assert not llm.calls


def test_rejects_questions_that_reference_unknown_analysis_ids():
    generation = TechnicalQuestionGeneration.model_validate(valid_output())
    generation.questions[0].experience_ids = ["E99"]

    with pytest.raises(TechnicalQuestionValidationError, match="없는 experience ID"):
        validate_technical_question_generation(generation, EXPERIENCES, REQUIREMENTS)


def test_rejects_forbidden_question_topics():
    generation = TechnicalQuestionGeneration.model_validate(valid_output())
    generation.questions[0].text = "결혼 여부와 지원자 이탈률의 관계를 분석해 보셨나요?"

    with pytest.raises(TechnicalQuestionValidationError, match="금지 주제"):
        validate_technical_question_generation(generation, EXPERIENCES, REQUIREMENTS)


def test_insufficient_llm_result_cannot_contain_questions():
    generation = TechnicalQuestionGeneration.model_validate(valid_output(status="insufficient_analysis"))

    with pytest.raises(TechnicalQuestionValidationError, match="질문이 없어야"):
        validate_technical_question_generation(generation, EXPERIENCES, REQUIREMENTS)


def test_validator_rejects_wrong_question_count():
    generation = TechnicalQuestionGeneration.model_validate(valid_output())
    generation.questions.pop()

    with pytest.raises(TechnicalQuestionValidationError, match="정확히 2개"):
        validate_technical_question_generation(generation, EXPERIENCES, REQUIREMENTS)


def test_validator_returns_questions_with_source_links_and_issued_ids():
    generation = TechnicalQuestionGeneration.model_validate(valid_output())

    result = validate_technical_question_generation(generation, EXPERIENCES, REQUIREMENTS)

    assert [question.question_id for question in result.questions] == ["TQ-001", "TQ-002"]
    assert result.questions[0].experience_ids == ["E1"]


def test_generation_schema_rejects_unknown_fields():
    with pytest.raises(ValueError):
        TechnicalQuestionGeneration.model_validate({**valid_output(), "extra": True})