"""분석 그래프의 결과물: 면접 설계도(InterviewBlueprint).

분석 그래프가 JD, 이력서, 자기소개서를 읽고 만들며, 면접 그래프는 이것만 입력으로 받습니다.
문서 원문은 여기에 들어가지 않습니다 (세션 종료 후 원문 삭제 원칙).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CATEGORY_ORDER = ["performance", "relationship", "adaptability", "leadership"]
CATEGORY_NAMES = {
    "performance": "성과역량",
    "relationship": "관계역량",
    "adaptability": "적응역량",
    "leadership": "리더십역량",
}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- 문서 분석


class VerificationPoint(_Model):
    """면접에서 확인할 주장. 서류 분석에서 주로 만들고, 자기소개에서 새로 나온 주장을 추가합니다."""

    id: str = Field(description="예: V1")
    source: Literal["documents", "intro"] = "documents"
    claim: str = Field(description="지원자의 주장")
    concern: str = Field(description="무엇이 불확실하거나 JD 와 맞지 않는지")
    category_codes: list[str] = Field(description="확인하기 좋은 영역")
    requirement_ids: list[str] = Field(default_factory=list)
    experience_ids: list[str] = Field(default_factory=list)
    status: Literal["pending", "probed"] = "pending"
    probed_in: str | None = Field(None, description="확인 질문을 한 thread_id")


class JDRequirement(_Model):
    id: str = Field(description="예: R1")
    text: str = Field(description="요구사항 요약. 예: 대규모 채용 프로세스 운영 경험")
    kind: Literal["duty", "skill", "experience", "trait", "culture"]
    importance: Literal["must", "preferred"]
    competency_codes: list[str] = Field(default_factory=list, description="관련 소분류 코드")


class CompanyContext(_Model):
    company_name: str | None = None
    role_title: str | None = None
    mission_or_values: list[str] = Field(default_factory=list, description="JD 에 드러난 회사의 지향점")
    business_summary: str | None = None


class Experience(_Model):
    id: str = Field(description="예: E1")
    source: Literal["resume", "cover_letter"]
    title: str = Field(description="예: 채용 프로세스 개편 프로젝트")
    organization: str | None = None
    period: str | None = None
    summary: str
    claimed_results: list[str] = Field(default_factory=list, description="지원자가 주장한 성과")
    competency_codes: list[str] = Field(default_factory=list)


class RequirementLink(_Model):
    requirement_id: str
    experience_ids: list[str] = Field(default_factory=list)
    strength: Literal["strong", "partial", "gap"]
    note: str = Field(description="연결 근거, 또는 부족한 점")


# ---------------------------------------------------------------- 질문 계획과 평가 기준


class PlannedQuestion(_Model):
    question_id: str = Field(description="문항 은행 ID. 평가 기준(체크포인트)은 항상 원본 문항을 따름")
    category_code: str
    competency_code: str
    personalized_text: str | None = Field(
        None, description="이력서 경험에 맞춰 다듬은 질문. None 이면 원본 질문을 그대로 사용"
    )
    anchor_experience_id: str | None = Field(None, description="개인화에 쓴 경험")
    target_requirement_ids: list[str] = Field(default_factory=list)
    verification_point_ids: list[str] = Field(default_factory=list, description="이 문항에서 확인하기 좋은 검증 포인트")
    reason: str | None = None
    validation: Literal["not_needed", "passed", "reverted"] = Field(
        "not_needed", description="개인화 문구 검증 결과. reverted 면 원본 문구로 되돌림"
    )
    validation_notes: list[str] = Field(default_factory=list)


class QuestionValidation(_Model):
    """개인화 질문 검증 결과 (검증 에이전트 출력)."""

    passed: bool
    jd_relevant: bool = Field(description="JD 요구사항과 관련 있는가")
    grounded: bool = Field(description="이력서, 자소서에 실제로 있는 경험만 언급하는가 (지어낸 사실 없음)")
    intent_preserved: bool = Field(description="원본 문항의 질문 의도와 체크포인트로 채점할 수 있는가")
    lawful: bool = Field(description="채용절차법 금지 항목이나 차별 소지가 없는가")
    issues: list[str] = Field(default_factory=list, description="실패한 이유. 재개인화 때 그대로 전달")


class CategoryPlan(_Model):
    category_code: str
    primary: list[PlannedQuestion] = Field(description="기본으로 묻는 문항 (기본 2개)")
    reserve: list[PlannedQuestion] = Field(
        default_factory=list, description="근거가 부족할 때 추가로 묻는 예비 문항"
    )


class RubricAnchor(_Model):
    score: int = Field(ge=1, le=5)
    description: str


DEFAULT_BARS = [
    RubricAnchor(score=5, description="STAR 가 모두 구체적이고 Positive 체크포인트 다수 충족, 본인 역할과 성과가 명확"),
    RubricAnchor(score=4, description="대부분 구체적이고 Positive 체크포인트를 충족, 일부 결과나 수치가 약함"),
    RubricAnchor(score=3, description="경험은 있으나 행동이나 결과가 일반적, Positive 와 Negative 가 섞임"),
    RubricAnchor(score=2, description="상황 설명 위주로 본인 행동이 불분명, Negative 체크포인트가 두드러짐"),
    RubricAnchor(score=1, description="관련 경험이 없거나 답변 회피, Negative 체크포인트 다수"),
]


class QuestionRubric(_Model):
    question_id: str
    base_checkpoint_ids: list[str] = Field(description="문항 은행 체크포인트 (세션 간 비교 가능한 기준)")
    jd_criteria: list[str] = Field(
        default_factory=list, description="JD 맞춤 보조 기준. 점수 해석과 피드백에만 쓰고 기본 척도는 바꾸지 않음"
    )


class IntroRubric(_Model):
    """자기소개 평가 기준. JD 를 쓴 회사 담당자 관점. 합불에는 반영하지 않음."""

    company_perspective: str = Field(description="이 회사가 지원자에게 듣고 싶은 것")
    criteria: list[str] = Field(description="예: 이 회사여야 하는 이유가 회사 고유의 특징과 연결되는가")
    expected_links: list[str] = Field(
        default_factory=list, description="자기소개에서 연결해 주면 좋을 이력 경험과 JD 요구사항 쌍"
    )


class Rubric(_Model):
    scale: list[RubricAnchor] = Field(default_factory=lambda: list(DEFAULT_BARS))
    questions: list[QuestionRubric] = Field(default_factory=list)
    intro: IntroRubric


class GuideItem(_Model):
    topic: str
    count: int
    note: str | None = None


class InterviewGuide(_Model):
    """면접 시작 전 안내. 질문 주제, 문항 수, 예상 시간만 공개하고 질문 내용은 공개하지 않음."""

    items: list[GuideItem]
    expected_minutes: tuple[int, int] = Field(description="예상 소요 시간 범위 (분)")
    answer_rules: list[str]


class InterviewBlueprint(_Model):
    personalized: bool = Field(description="문서 분석으로 개인화했는지. 문서 없이 시작하면 False")
    target_role: str | None = None
    company: CompanyContext = Field(default_factory=CompanyContext)
    requirements: list[JDRequirement] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    links: list[RequirementLink] = Field(default_factory=list)
    verification_points: list[VerificationPoint] = Field(default_factory=list)
    plan: list[CategoryPlan]
    rubric: Rubric
    guide: InterviewGuide

    def category_plan(self, category_code: str) -> CategoryPlan:
        return next(p for p in self.plan if p.category_code == category_code)
