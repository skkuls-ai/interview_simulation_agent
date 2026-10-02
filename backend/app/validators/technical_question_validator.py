"""Validate generated technical questions against the document analysis."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.llm.client import JsonLLM
from app.schemas.state import Analysis, ClaimType, Question, QuestionType

QUESTION_COUNT = 2
_FORBIDDEN = re.compile(
	r"나이|연세|몇\s*살|출신\s*지역|고향|혼인|결혼|배우자|임신|출산|부모님|가족|"
	r"종교|정치\s*(성향|견해)|재산|체중|몸무게|외모|용모"
)


class _Model(BaseModel):
	model_config = ConfigDict(extra="forbid")


class TechnicalQuestionDraft(_Model):
	text: str = Field(min_length=10, max_length=120)
	claim_ids: list[str] = Field(min_length=1)
	checkpoint_ids: list[str] = Field(min_length=1)
	requirement_ids: list[str] = Field(default_factory=list)
	criteria: list[str] = Field(min_length=1, max_length=4)


class TechnicalQuestionGeneration(_Model):
	status: Literal["ready", "insufficient_analysis"]
	reason: str
	questions: list[TechnicalQuestionDraft]


class TechnicalQuestionGroundingReview(_Model):
	is_valid: bool
	reason: str
	unsupported_details: list[str]


GROUNDING_REVIEW_SYSTEM = """\
당신은 기술 면접 질문을 검수하는 독립적인 시니어 엔지니어입니다.
지원자에게 질문을 추가로 만들지 말고, 생성된 각 질문의 전제가 제공된 분석 근거에 있는지만 검토합니다.

검수 규칙:
1. 분석에 없는 기술, 제품, 알고리즘, 규모, 수치, 성과, 본인 역할을 질문이 이미 사실인 것처럼 전제하면 무효입니다.
2. 서류에 적힌 주장을 되짚거나, 서류에 빠진 세부사항을 질문으로 확인하는 것은 허용합니다.
3. 각 질문이 참조한 claim과 checkpoint가 질문의 실제 주제를 뒷받침하는지 확인합니다.
4. 확인할 수 없는 부분은 지원자가 설명하도록 열린 질문으로 물어야 하며, 사실로 단정하면 안 됩니다.
5. 애매하면 통과시키지 말고 unsupported_details에 근거 없는 전제를 구체적으로 적습니다.
"""


class TechnicalQuestionValidationResult(_Model):
	is_valid: bool
	status: Literal["ready", "insufficient_analysis"]
	reason: str
	questions: list[Question]


class TechnicalQuestionValidationError(ValueError):
	"""Raised when generated questions violate the technical-question contract."""


def _grounding_review_prompt(
	analysis: Analysis,
	generation: TechnicalQuestionGeneration,
) -> str:
	technical_claim_ids = {claim.claim_id for claim in analysis.claims if ClaimType.TECH in claim.types}
	checkpoints = [
		checkpoint for checkpoint in analysis.checkpoints
		if technical_claim_ids.intersection(checkpoint.claim_ids)
	]
	supported_claim_ids = {claim_id for checkpoint in checkpoints for claim_id in checkpoint.claim_ids}
	claims = [claim for claim in analysis.claims if claim.claim_id in supported_claim_ids]
	linked_requirement_ids = {
		link.requirement_id for link in analysis.links
		if technical_claim_ids.intersection(link.claim_ids)
	}
	requirements = [
		requirement for requirement in analysis.requirements
		if requirement.requirement_id in linked_requirement_ids
	]
	requirement_claim_links = [
		{
			"requirement_id": link.requirement_id,
			"claim_ids": [claim_id for claim_id in link.claim_ids if claim_id in technical_claim_ids],
		}
		for link in analysis.links if link.requirement_id in linked_requirement_ids
	]
	return "\n".join([
		"## 허용된 기술 주장 (원문 인용)",
		json.dumps([claim.model_dump(mode="json") for claim in claims], ensure_ascii=False, indent=2),
		"## 연결된 직무 요구사항",
		json.dumps([requirement.model_dump(mode="json") for requirement in requirements], ensure_ascii=False, indent=2),
		"## 요구사항-주장 연결표",
		json.dumps(requirement_claim_links, ensure_ascii=False, indent=2),
		"## 검증 포인트",
		json.dumps([checkpoint.model_dump(mode="json") for checkpoint in checkpoints], ensure_ascii=False, indent=2),
		"## 검수할 기술 질문 초안",
		json.dumps([question.model_dump(mode="json") for question in generation.questions], ensure_ascii=False, indent=2),
	])


def review_technical_question_grounding(
	llm: JsonLLM,
	analysis: Analysis,
	generation: TechnicalQuestionGeneration,
) -> TechnicalQuestionGroundingReview:
	"""Use the dedicated validator model role to review semantic grounding."""
	review, _ = llm.generate_json(
		"validator",
		GROUNDING_REVIEW_SYSTEM,
		_grounding_review_prompt(analysis, generation),
		TechnicalQuestionGroundingReview,
	)
	return review


def _normalized_question(text: str) -> str:
	return "".join(
		char.casefold() for char in text
		if not char.isspace() and not unicodedata.category(char).startswith("P")
	)


def validate_technical_questions(
	generation: TechnicalQuestionGeneration,
	analysis: Analysis,
) -> TechnicalQuestionValidationResult:
	def invalid(reason: str) -> TechnicalQuestionValidationResult:
		return TechnicalQuestionValidationResult(
			is_valid=False, status=generation.status, reason=reason, questions=[],
		)

	if generation.status == "insufficient_analysis":
		if generation.questions:
			return invalid("분석 부족 결과에는 생성 질문이 없어야 합니다.")
		return TechnicalQuestionValidationResult(
			is_valid=True, status=generation.status, reason=generation.reason, questions=[],
		)

	if len(generation.questions) != QUESTION_COUNT:
		return invalid(f"기술 질문은 정확히 {QUESTION_COUNT}개여야 합니다.")

	claims = {claim.claim_id: claim for claim in analysis.claims}
	technical_claim_ids = {claim_id for claim_id, claim in claims.items() if ClaimType.TECH in claim.types}
	checkpoints = {checkpoint.checkpoint_id: checkpoint for checkpoint in analysis.checkpoints}
	requirements = {requirement.requirement_id for requirement in analysis.requirements}
	requirement_links = {link.requirement_id: set(link.claim_ids) for link in analysis.links}
	seen_texts: set[str] = set()
	questions: list[Question] = []

	for index, draft in enumerate(generation.questions, start=1):
		normalized = _normalized_question(draft.text)
		if normalized in seen_texts:
			return invalid("중복 기술 질문이 있습니다.")
		seen_texts.add(normalized)

		claim_ids = set(draft.claim_ids)
		if len(claim_ids) != len(draft.claim_ids):
			return invalid("claim_id가 중복되었습니다.")
		if not claim_ids <= claims.keys():
			return invalid("입력 분석에 없는 claim_id를 참조했습니다.")
		if not claim_ids & technical_claim_ids:
			return invalid("각 질문은 최소 하나의 TECH 유형 claim을 참조해야 합니다.")

		checkpoint_ids = set(draft.checkpoint_ids)
		if len(checkpoint_ids) != len(draft.checkpoint_ids):
			return invalid("checkpoint_id가 중복되었습니다.")
		if not checkpoint_ids <= checkpoints.keys():
			return invalid("입력 분석에 없는 checkpoint_id를 참조했습니다.")
		if any(not claim_ids.intersection(checkpoints[cp_id].claim_ids) for cp_id in checkpoint_ids):
			return invalid("질문이 참조한 검증 포인트가 연결한 claim과 일치하지 않습니다.")

		requirement_ids = set(draft.requirement_ids)
		if len(requirement_ids) != len(draft.requirement_ids):
			return invalid("requirement_id가 중복되었습니다.")
		if not requirement_ids <= requirements:
			return invalid("입력 분석에 없는 requirement_id를 참조했습니다.")
		if any(not claim_ids.intersection(requirement_links.get(req_id, set())) for req_id in requirement_ids):
			return invalid("질문의 주장과 연결되지 않은 직무 요구사항을 참조했습니다.")

		if _FORBIDDEN.search(draft.text):
			return invalid("직무와 무관하거나 차별 소지가 있는 금지 주제가 포함되어 있습니다.")

		questions.append(Question(
			question_id=f"Q-{index + 3}",
			order=index + 3,
			type=QuestionType.TECH,
			text=draft.text.strip(),
			checkpoint_ids=draft.checkpoint_ids,
			question_bank_id=f"TECH-ANALYSIS-{index:03d}",
			criteria=draft.criteria,
		))

	return TechnicalQuestionValidationResult(
		is_valid=True, status=generation.status, reason=generation.reason, questions=questions,
	)


__all__ = [
	"TechnicalQuestionDraft",
	"TechnicalQuestionGeneration",
	"TechnicalQuestionGroundingReview",
	"TechnicalQuestionValidationError",
	"TechnicalQuestionValidationResult",
	"review_technical_question_grounding",
	"validate_technical_questions",
]
