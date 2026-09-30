"""Generate two technical interview questions from document-analysis results."""

from __future__ import annotations

import json

from ..schemas.state import Analysis, ClaimType
from ..validators.technical_question_validator import (
    TechnicalQuestionGeneration,
    TechnicalQuestionValidationError,
    TechnicalQuestionValidationResult,
    review_technical_question_grounding,
    validate_technical_questions,
)
from .client import JsonLLM

SYSTEM = """\
당신은 AI·백엔드 시스템을 채용하는 시니어 소프트웨어 엔지니어 면접관입니다.
지원자가 실제로 수행했다고 서류에 적은 기술 경험을 깊이 확인하는 질문을 만듭니다.
기술 면접의 초점은 설계 선택, 구현 과정, 실패 처리, 측정 방법과 트레이드오프입니다.

규칙:
1. 입력에 제공된 기술 주장, 요구사항, 검증 포인트만 근거로 삼습니다. 새 도구, 프레임워크, 알고리즘, 수치, 성과, 역할을 사실처럼 추가하지 않습니다.
2. 질문은 서류에 있는 주장에 관해 설명을 요청합니다. 서류에 없는 세부사항은 전제로 단정하지 말고 질문으로 확인합니다.
3. 서로 다른 기술 경험 또는 서로 다른 검증 포인트를 겨냥하는 질문을 정확히 2개 만듭니다.
4. 각 질문은 입력된 TECH 주장(claim_id)과 그 주장을 실제로 참조하는 검증 포인트(checkpoint_id)를 연결합니다.
5. requirement_id는 아래 요구사항-주장 연결표에 해당 claim_id가 명시된 경우에만 참조합니다. 연결이 없거나 불확실하면 빈 목록으로 둡니다.
6. 질문 하나에는 핵심 질문 하나만 담고, 존댓말과 120자 이내를 지킵니다.
7. 각 질문의 평가 기준(criteria)은 확인할 설명·근거·측정 방법으로 1~4개 작성합니다.
8. 분석 결과가 두 질문을 뒷받침하기에 부족하면 status=insufficient_analysis, questions=[]로 반환합니다.
9. 나이, 출신, 가족, 혼인, 종교 등 직무와 무관하거나 차별적인 질문은 만들지 않습니다.
"""

MAX_GROUNDING_ATTEMPTS = 2


def _prompt(analysis: Analysis, correction: str | None = None) -> str:
    tech_claim_ids = {c.claim_id for c in analysis.claims if ClaimType.TECH in c.types}
    checkpoints = [cp for cp in analysis.checkpoints if tech_claim_ids.intersection(cp.claim_ids)]
    checkpoint_claim_ids = {claim_id for cp in checkpoints for claim_id in cp.claim_ids}
    usable_claims = [c for c in analysis.claims if c.claim_id in checkpoint_claim_ids]
    related_requirement_ids = {
        link.requirement_id for link in analysis.links
        if tech_claim_ids.intersection(link.claim_ids)
    }
    requirements = [r for r in analysis.requirements if r.requirement_id in related_requirement_ids]
    requirement_claim_links = [
        {
            "requirement_id": link.requirement_id,
            "claim_ids": [claim_id for claim_id in link.claim_ids if claim_id in tech_claim_ids],
        }
        for link in analysis.links if link.requirement_id in related_requirement_ids
    ]
    sections = [
        "## 기술 관련 지원자 주장 (원문 인용)",
        json.dumps([claim.model_dump(mode="json") for claim in usable_claims], ensure_ascii=False, indent=2),
        "## 연결된 직무 요구사항",
        json.dumps([req.model_dump(mode="json") for req in requirements], ensure_ascii=False, indent=2),
        "## 직무 요구사항과 기술 주장 연결표 (이 표에 있는 쌍만 함께 참조 가능)",
        json.dumps(requirement_claim_links, ensure_ascii=False, indent=2),
        "## 연결된 검증 포인트",
        json.dumps([cp.model_dump(mode="json") for cp in checkpoints], ensure_ascii=False, indent=2),
    ]
    if correction:
        sections.extend(["## 이전 초안에서 수정할 근거 문제", correction])
    return "\n".join(sections)


class TechnicalQuestionAgent:
    """Create API-compatible Q-4 and Q-5 questions from a validated Analysis."""

    def __init__(self, llm: JsonLLM):
        self.llm = llm

    def generate(self, analysis: Analysis) -> TechnicalQuestionValidationResult:
        technical_claim_ids = {c.claim_id for c in analysis.claims if ClaimType.TECH in c.types}
        supported_ids = {
            claim_id for checkpoint in analysis.checkpoints for claim_id in checkpoint.claim_ids
        }
        if not technical_claim_ids.intersection(supported_ids):
            return TechnicalQuestionValidationResult(
                is_valid=True,
                status="insufficient_analysis",
                reason="기술 유형 주장과 이를 확인할 검증 포인트가 없어 기술 질문을 만들 수 없습니다.",
                questions=[],
            )

        correction = None
        last_issue = ""
        for _ in range(MAX_GROUNDING_ATTEMPTS):
            generation, _ = self.llm.generate_json(
                "analysis", SYSTEM, _prompt(analysis, correction), TechnicalQuestionGeneration,
            )
            result = validate_technical_questions(generation, analysis)
            if not result.is_valid:
                correction = result.reason
                last_issue = result.reason
                continue
            if result.status == "insufficient_analysis":
                return result

            review = review_technical_question_grounding(self.llm, analysis, generation)
            if review.is_valid:
                return result
            last_issue = "; ".join([review.reason, *review.unsupported_details]).strip("; ")
            correction = last_issue

        raise TechnicalQuestionValidationError(
            f"기술 질문이 분석 근거 검증을 통과하지 못했습니다: {last_issue}"
        )