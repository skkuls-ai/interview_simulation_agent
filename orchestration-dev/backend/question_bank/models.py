"""면접 질문 은행 데이터 모델.

이 파일이 스키마의 원본(source of truth)입니다.
schema.json 은 여기서 자동 생성되므로 직접 수정하지 말고 이 파일을 고친 뒤 convert.py 를 다시 실행하세요.
"""

from __future__ import annotations

from enum import Enum
from functools import cached_property
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.1.0"


class QuestionType(str, Enum):
    """질문 유형. 꼬리질문 전략이 유형별로 달라집니다."""

    BEHAVIORAL = "behavioral"  # 경험면접: 과거 행동을 STAR 로 확인
    SITUATIONAL = "situational"  # 상황면접: 가상 상황에서의 판단, 이유, 대안 확인


QUESTION_TYPE_LABELS: dict[QuestionType, str] = {
    QuestionType.BEHAVIORAL: "경험면접",
    QuestionType.SITUATIONAL: "상황면접",
}


class FollowUpKind(str, Enum):
    """원본 추가 질문 앞의 괄호 표기를 분류한 값."""

    CONDITION = "condition"  # (성취했다면), (수용하지 않는다면) 처럼 앞 답변에 따라 쓸지 말지 결정
    PRESSURE = "pressure"  # (압박 질문)
    ROLE_PLAY = "role_play"  # (제가 동료라고 생각하고) 처럼 면접관이 역할을 맡는 질문


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FollowUp(_Base):
    id: str = Field(description="예: Q001-F1", pattern=r"^Q\d{3}-F\d+$")
    order: int = Field(ge=1, description="원본 번호")
    text: str = Field(description="면접관이 실제로 말할 문장 (괄호 표기 제거, 공백 정리)")
    kind: FollowUpKind | None = Field(
        default=None, description="괄호 표기가 있을 때만 값이 있음. 없으면 일반 꼬리질문"
    )
    note: str | None = Field(
        default=None,
        description="괄호 안의 원문. kind=condition 이면 사용 조건, role_play 면 면접관이 맡을 역할",
    )
    raw_text: str = Field(description="엑셀 원문 그대로 (번호만 제거)")


class Intent(_Base):
    id: str = Field(description="예: Q001-I1", pattern=r"^Q\d{3}-I\d+$")
    text: str = Field(description="질문 의도. 평가 에이전트가 무엇을 확인해야 하는지")


class Checkpoint(_Base):
    id: str = Field(
        description="예: Q001-P1 (Positive), Q001-N1 (Negative). 평가 근거 인용 시 이 ID 를 씀",
        pattern=r"^Q\d{3}-[PN]\d+$",
    )
    text: str


class Checkpoints(_Base):
    positive: list[Checkpoint] = Field(min_length=1, description="높은 점수의 행동 지표")
    negative: list[Checkpoint] = Field(min_length=1, description="낮은 점수의 행동 지표")


class Question(_Base):
    id: str = Field(description="예: Q001", pattern=r"^Q\d{3}$")
    no: int = Field(ge=1, description="엑셀 원본 No")
    category_code: str = Field(description="대분류 코드. 예: performance")
    category_name: str = Field(description="대분류 이름. 예: 성과역량")
    competency_code: str = Field(description="소분류 코드. 예: positivity")
    competency_name: str = Field(description="소분류 이름. 예: 긍정성")
    question_type: QuestionType
    question_type_label: Literal["경험면접", "상황면접"]
    text: str = Field(description="메인 질문 (면접관이 읽는 문장)")
    fallback_text: str | None = Field(
        None, description="원문의 '(답변하지 못할 경우) …' 안내. 지원자가 경험이 없다고 할 때만 사용"
    )
    duplicate_of: str | None = Field(
        None, description="원본 엑셀에서 질문, 의도, 체크포인트가 모두 같은 앞 문항 ID. 문항 선정에서 제외"
    )
    follow_ups_shared_with: str | None = Field(
        None,
        description="추가 질문 목록을 다른 문항과 공유할 때 그 문항 ID. 사용은 하되, 꼬리질문 판단 에이전트가 "
                    "이 문항의 맥락에 맞는 것만 고름 (예: 팀 과제 전제 질문은 상황면접에 맞지 않음)",
    )
    follow_ups: list[FollowUp] = Field(min_length=1, description="원본 추가 질문 (꼬리질문 후보)")
    intents: list[Intent] = Field(min_length=1)
    checkpoints: Checkpoints

    @model_validator(mode="after")
    def _check_child_ids(self) -> "Question":
        children = (
            [f.id for f in self.follow_ups]
            + [i.id for i in self.intents]
            + [c.id for c in self.checkpoints.positive]
            + [c.id for c in self.checkpoints.negative]
        )
        bad = [cid for cid in children if not cid.startswith(self.id + "-")]
        if bad:
            raise ValueError(f"{self.id}: 하위 ID 접두어 불일치 {bad}")
        if QUESTION_TYPE_LABELS[self.question_type] != self.question_type_label:
            raise ValueError(f"{self.id}: question_type 과 label 불일치")
        return self


class Competency(_Base):
    code: str
    name: str
    description: str = Field(description="소분류 설명 (역량 정의)")
    question_ids: list[str] = Field(min_length=1)


class Category(_Base):
    code: str
    name: str
    competencies: list[Competency] = Field(min_length=1)


class QuestionBank(_Base):
    schema_version: str = SCHEMA_VERSION
    source_file: str
    source_sha256: str = Field(description="원본 엑셀 해시. 원본이 바뀌었는지 확인용")
    categories: list[Category]
    questions: list[Question]
    quality_warnings: list[str] = Field(default_factory=list, description="원본 데이터 점검 결과")

    @model_validator(mode="after")
    def _check_integrity(self) -> "QuestionBank":
        ids = [q.id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("질문 ID 중복")
        by_id = {q.id: q for q in self.questions}
        listed: list[str] = []
        for cat in self.categories:
            for comp in cat.competencies:
                for qid in comp.question_ids:
                    q = by_id.get(qid)
                    if q is None:
                        raise ValueError(f"{comp.code}: 없는 질문 {qid}")
                    if (q.category_code, q.competency_code) != (cat.code, comp.code):
                        raise ValueError(f"{qid}: 분류 불일치")
                    listed.append(qid)
        if sorted(listed) != sorted(ids):
            raise ValueError("분류 트리와 질문 목록이 일치하지 않음")
        return self

    # 런타임 조회용 헬퍼 (에이전트에서 사용)

    @cached_property
    def _by_id(self) -> dict[str, Question]:
        return {q.id: q for q in self.questions}

    def get(self, question_id: str) -> Question:
        return self._by_id[question_id]

    def by_competency(self, competency_code: str, include_duplicates: bool = False) -> list[Question]:
        return [
            q for q in self.questions
            if q.competency_code == competency_code and (include_duplicates or q.duplicate_of is None)
        ]

    def by_category(self, category_code: str) -> list[Question]:
        return [q for q in self.questions if q.category_code == category_code]

    @classmethod
    def load(cls, path: str) -> "QuestionBank":
        with open(path, encoding="utf-8") as f:
            return cls.model_validate_json(f.read())
