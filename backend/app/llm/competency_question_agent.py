"""Select two job-relevant competency questions from the existing question bank."""

from __future__ import annotations

import json

from app.banks.competency_question_bank import CompetencyQuestionBank, load_competency_question_bank
from app.schemas.state import Analysis
from app.validators.competency_question_validator import (
    CompetencyQuestionGeneration,
    CompetencyQuestionValidationError,
    CompetencyQuestionValidationResult,
    validate_competency_question_selection,
)
from .client import JsonLLM

SYSTEM = """\
당신은 엔지니어 채용을 담당하는 구조화 면접관입니다.
직무 수행에 필요한 문제해결, 협업, 의사소통, 학습·적응 행동을 확인할 기존 역량 질문을 고릅니다.
성격 유형을 진단하거나 막연한 '조직 적합성'을 추측하지 않습니다.
질문을 새로 쓰거나 표현을 바꾸지 말고, 반드시 제공된 질문은행 번호 중에서 선택합니다.

규칙:
1. 직무 요구사항과 인재상(TALENT)을 우선 읽고, 실제 업무 행동과 연결되는 역량을 찾습니다.
2. 지원자 주장은 질문 맥락을 맞추는 참고 자료일 뿐, 사실이나 성격을 단정하는 근거로 쓰지 않습니다.
3. 질문 은행에서 서로 다른 소분류 역량을 확인하는 질문을 정확히 2개 고릅니다.
4. 상황면접과 경험면접 중 직무 요구를 가장 잘 확인할 유형을 고릅니다.
5. 각 선택은 입력된 requirement_id 하나 이상과 연결하고, 선택 근거를 간결하게 씁니다.
6. 직무 요구사항이 질문 선택을 뒷받침하지 못하면 status=insufficient_analysis, selections=[]로 반환합니다.
7. 나이, 출신, 가족, 혼인, 종교 등 직무와 무관하거나 차별적인 주제를 묻는 질문은 선택하지 않습니다.
"""


def _prompt(analysis: Analysis, bank: CompetencyQuestionBank) -> str:
    return "\n".join([
        "## 직무 요구사항",
        json.dumps([item.model_dump(mode="json") for item in analysis.requirements], ensure_ascii=False, indent=2),
        "## 지원자 주장 (질문 맥락 참고용)",
        json.dumps([item.model_dump(mode="json") for item in analysis.claims], ensure_ascii=False, indent=2),
        "## 기존 질문은행 후보 (문항을 수정하지 말고 번호만 선택)",
        json.dumps([item.selection_payload() for item in bank.questions], ensure_ascii=False, indent=1),
    ])


class CompetencyQuestionAgent:
    def __init__(self, llm: JsonLLM, bank: CompetencyQuestionBank | None = None):
        self.llm = llm
        self.bank = bank or load_competency_question_bank()

    def generate(self, analysis: Analysis) -> CompetencyQuestionValidationResult:
        if not analysis.requirements:
            return CompetencyQuestionValidationResult(
                is_valid=True,
                status="insufficient_analysis",
                reason="직무 요구사항 분석 결과가 없어 적합한 역량 질문을 고를 수 없습니다.",
                questions=[],
            )

        generation, _ = self.llm.generate_json(
            "analysis", SYSTEM, _prompt(analysis, self.bank), CompetencyQuestionGeneration,
        )
        result = validate_competency_question_selection(generation, analysis, self.bank)
        if not result.is_valid:
            raise CompetencyQuestionValidationError(result.reason)
        return result