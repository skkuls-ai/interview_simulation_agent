from __future__ import annotations

from app.banks.competency_question_bank import load_competency_question_bank
from app.llm.competency_question_agent import CompetencyQuestionAgent
from app.nodes.prep.competency_questions import build_competency_question_node
from app.schemas.state import Analysis, Requirement
from app.validators.competency_question_validator import (
    CompetencyQuestionGeneration,
    validate_competency_question_selection,
)


BANK = load_competency_question_bank()
ANALYSIS = Analysis(requirements=[
    Requirement(requirement_id="RQ-001", text="RAG 검색 품질을 측정하고 개선", source_doc="job_description", kind="SKILL"),
    Requirement(requirement_id="RQ-002", text="팀원과 근거를 나누며 함께 결정", source_doc="job_posting", kind="TALENT"),
])
OUTPUT = {
    "status": "ready",
    "reason": "문제 해결과 협력 역량이 직무 요구와 연결됩니다.",
    "selections": [
        {"question_number": 26, "requirement_ids": ["RQ-001"], "rationale": "문제 원인을 분석하고 해결하는 역량을 확인합니다."},
        {"question_number": 86, "requirement_ids": ["RQ-002"], "rationale": "팀 협업에서 역할과 조율 방식을 확인합니다."},
    ],
}


class FakeLLM:
    def __init__(self, output=OUTPUT):
        self.output = output
        self.calls = []

    def generate_json(self, role, system, prompt, schema):
        self.calls.append((role, system, prompt, schema))
        return schema.model_validate(self.output), None


def test_question_bank_loads_all_rows_and_ids():
    assert len(BANK.questions) == 150
    assert BANK.questions[0].number == 1
    assert BANK.questions[-1].number == 150
    assert BANK.by_number(26).competency == "문제해결력"


def test_agent_selects_two_questions_mapped_to_app_contract():
    llm = FakeLLM()

    result = CompetencyQuestionAgent(llm, BANK).generate(ANALYSIS)

    assert result.is_valid and result.status == "ready"
    assert [(question.question_id, question.order, question.type.value) for question in result.questions] == [
        ("Q-2", 2, "BEHAVIOR"), ("Q-3", 3, "BEHAVIOR"),
    ]
    assert [question.question_bank_id for question in result.questions] == [
        "COMP-문제해결력-026", "COMP-협력성-086",
    ]
    assert result.questions[0].criteria and len(result.selection_reasons) == 2
    assert llm.calls[0][0] == "analysis"
    assert "RAG 검색 품질을 측정하고 개선" in llm.calls[0][2]


def test_agent_returns_insufficient_when_job_analysis_is_empty():
    llm = FakeLLM()

    result = CompetencyQuestionAgent(llm, BANK).generate(Analysis())

    assert result.status == "insufficient_analysis"
    assert result.questions == []
    assert not llm.calls


def test_validator_rejects_duplicate_questions_and_competencies():
    same_question = CompetencyQuestionGeneration.model_validate({
        **OUTPUT,
        "selections": [OUTPUT["selections"][0], OUTPUT["selections"][0]],
    })
    duplicate_result = validate_competency_question_selection(same_question, ANALYSIS, BANK)
    assert not duplicate_result.is_valid

    same_competency = CompetencyQuestionGeneration.model_validate({
        **OUTPUT,
        "selections": [
            OUTPUT["selections"][0],
            {"question_number": 27, "requirement_ids": ["RQ-001"], "rationale": "같은 소분류 질문"},
        ],
    })
    competency_result = validate_competency_question_selection(same_competency, ANALYSIS, BANK)
    assert not competency_result.is_valid
    assert "서로 다른 역량" in competency_result.reason


def test_node_returns_partial_state_for_analysis_pipeline():
    result = build_competency_question_node(FakeLLM(),)( {"analysis": ANALYSIS} )

    assert result["competency_question_status"] == "ready"
    assert [question.question_id for question in result["competency_questions"]] == ["Q-2", "Q-3"]