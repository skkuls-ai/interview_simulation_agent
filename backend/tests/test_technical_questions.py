from __future__ import annotations

import pytest

from app.llm.technical_question_agent import TechnicalQuestionAgent
from app.nodes.prep.technical_questions import build_technical_question_node
from app.schemas.state import Analysis, Checkpoint, Claim, Requirement
from app.validators.technical_question_validator import (
    TechnicalQuestionGeneration,
    TechnicalQuestionGroundingReview,
    validate_technical_questions,
)


ANALYSIS = Analysis(
    requirements=[Requirement(requirement_id="RQ-001", text="검색 품질 개선", source_doc="job_description", kind="SKILL")],
    claims=[
        Claim(claim_id="CL-001", source_doc="resume", text="RAG 검색 파이프라인을 설계했습니다", types=["TECH"]),
        Claim(claim_id="CL-002", source_doc="resume", text="검색 정확도를 20% 개선했습니다", types=["TECH", "METRIC"]),
    ],
    checkpoints=[
        Checkpoint(checkpoint_id="CP-001", claim_ids=["CL-001"], title="검색 구성", what_to_verify="RAG 구성과 근거를 확인합니다."),
        Checkpoint(checkpoint_id="CP-002", claim_ids=["CL-002"], title="품질 측정", what_to_verify="정확도 측정 기준을 확인합니다."),
    ],
    links=[{"requirement_id": "RQ-001", "claim_ids": ["CL-001", "CL-002"]}],
)

OUTPUT = {
    "status": "ready",
    "reason": "두 개의 기술 주장을 확인할 수 있습니다.",
    "questions": [
        {
            "text": "RAG 검색 파이프라인에서 검색 결과의 순위를 어떻게 결정하셨나요?",
            "claim_ids": ["CL-001"],
            "checkpoint_ids": ["CP-001"],
            "requirement_ids": ["RQ-001"],
            "criteria": ["검색 순위 산정 방식", "대안 비교 근거"],
        },
        {
            "text": "검색 정확도를 20% 개선했다는 결과를 어떤 데이터와 지표로 측정하셨나요?",
            "claim_ids": ["CL-002"],
            "checkpoint_ids": ["CP-002"],
            "requirement_ids": ["RQ-001"],
            "criteria": ["평가 데이터 구성", "측정 지표의 재현성"],
        },
    ],
}


class FakeLLM:
    def __init__(self, outputs=None, reviews=None):
        self.outputs = list(outputs or [OUTPUT])
        self.reviews = list(reviews or [{"is_valid": True, "reason": "근거와 일치합니다.", "unsupported_details": []}])
        self.calls = []

    def generate_json(self, role, system, prompt, schema):
        self.calls.append((role, system, prompt, schema))
        if schema is TechnicalQuestionGroundingReview:
            output = self.reviews.pop(0)
        else:
            output = self.outputs.pop(0)
        return schema.model_validate(output), None


def test_agent_returns_app_question_contract_from_analysis():
    llm = FakeLLM()

    result = TechnicalQuestionAgent(llm).generate(ANALYSIS)

    assert result.is_valid and result.status == "ready"
    assert [(question.question_id, question.order, question.type.value) for question in result.questions] == [
        ("Q-4", 4, "TECH"), ("Q-5", 5, "TECH"),
    ]
    assert result.questions[0].checkpoint_ids == ["CP-001"]
    assert result.questions[0].criteria
    assert llm.calls[0][0] == "analysis"
    assert "CL-001" in llm.calls[0][2] and "CP-001" in llm.calls[0][2]
    assert [call[0] for call in llm.calls] == ["analysis", "validator"]
    assert '"requirement_id": "RQ-001"' in llm.calls[0][2]
    assert '"claim_ids": [\n      "CL-001"' in llm.calls[0][2]


def test_agent_skips_llm_without_supported_technical_claims():
    analysis = ANALYSIS.model_copy(update={"claims": [], "checkpoints": []})
    llm = FakeLLM()

    result = TechnicalQuestionAgent(llm).generate(analysis)

    assert result.is_valid and result.status == "insufficient_analysis"
    assert result.questions == []
    assert not llm.calls


def test_graph_node_consumes_analysis_and_returns_partial_question_state():
    llm = FakeLLM()
    node = build_technical_question_node(llm)

    result = node({"analysis": ANALYSIS})

    assert set(result) == {
        "technical_question_status", "technical_question_reason", "technical_questions",
    }
    assert result["technical_question_status"] == "ready"
    assert [question.question_id for question in result["technical_questions"]] == ["Q-4", "Q-5"]


def test_validator_rejects_unknown_claim_and_checkpoint_references():
    generation = TechnicalQuestionGeneration.model_validate(OUTPUT)
    generation.questions[0].claim_ids = ["CL-999"]

    result = validate_technical_questions(generation, ANALYSIS)

    assert not result.is_valid
    assert "없는 claim_id" in result.reason


def test_validator_rejects_questions_without_related_checkpoints():
    generation = TechnicalQuestionGeneration.model_validate(OUTPUT)
    generation.questions[0].checkpoint_ids = ["CP-002"]

    result = validate_technical_questions(generation, ANALYSIS)

    assert not result.is_valid
    assert "연결한 claim" in result.reason


def test_validator_rejects_non_technical_claim_references():
    analysis = ANALYSIS.model_copy(update={
        "claims": [ANALYSIS.claims[0].model_copy(update={"types": ["ROLE"]}), ANALYSIS.claims[1]],
    })
    generation = TechnicalQuestionGeneration.model_validate(OUTPUT)

    result = validate_technical_questions(generation, analysis)

    assert not result.is_valid
    assert "TECH 유형 claim" in result.reason


def test_validator_requires_exactly_two_questions():
    generation = TechnicalQuestionGeneration.model_validate({**OUTPUT, "questions": OUTPUT["questions"][:1]})

    result = validate_technical_questions(generation, ANALYSIS)

    assert not result.is_valid
    assert "정확히 2개" in result.reason


def test_validator_rejects_forbidden_personal_topic():
    output = {**OUTPUT, "questions": [dict(question) for question in OUTPUT["questions"]]}
    output["questions"][0]["text"] = "부모님 직업과 RAG 검색 순위는 어떤 관계가 있나요?"
    generation = TechnicalQuestionGeneration.model_validate(output)

    result = validate_technical_questions(generation, ANALYSIS)

    assert not result.is_valid
    assert "금지 주제" in result.reason


def test_agent_regenerates_questions_flagged_for_unsupported_premise():
    hallucinated = {**OUTPUT, "questions": [dict(item) for item in OUTPUT["questions"]]}
    hallucinated["questions"][0]["text"] = "HNSW 인덱스의 efSearch 값을 어떻게 조정해 검색 정확도를 20% 개선하셨나요?"
    llm = FakeLLM(
        outputs=[hallucinated, OUTPUT],
        reviews=[
            {"is_valid": False, "reason": "근거에 없는 알고리즘을 전제합니다.", "unsupported_details": ["HNSW", "efSearch"]},
            {"is_valid": True, "reason": "서류 주장에 근거합니다.", "unsupported_details": []},
        ],
    )

    result = TechnicalQuestionAgent(llm).generate(ANALYSIS)

    assert result.is_valid
    assert [call[0] for call in llm.calls] == ["analysis", "validator", "analysis", "validator"]
    assert "HNSW" in llm.calls[2][2]


def test_agent_fails_closed_after_second_grounding_rejection():
    unsupported = {
        "is_valid": False,
        "reason": "지원서 근거가 없습니다.",
        "unsupported_details": ["기록되지 않은 서비스 규모"],
    }
    llm = FakeLLM(outputs=[OUTPUT, OUTPUT], reviews=[unsupported, unsupported])

    with pytest.raises(ValueError, match="근거 검증을 통과하지 못했습니다"):
        TechnicalQuestionAgent(llm).generate(ANALYSIS)