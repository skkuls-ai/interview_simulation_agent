"""docs/04 개발 계약의 준비 단계 모델 (임시 복사본).

⚠️ C 가 backend/app/schemas/state.py 를 올리면 이 파일을 지우고 그쪽을 import 합니다.
docs 의 코드를 글자 그대로 옮겼으므로 필드를 여기서 바꾸지 않습니다 (필드 변경은 팀 채널 → docs → 코드 순서).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


# ---------- 준비 단계 (A·B가 채움) ----------
class Requirement(BaseModel):
    requirement_id: str                 # RQ-001
    text: str
    source_doc: Literal["job_posting", "job_description"]
    kind: Literal["SKILL", "DUTY", "TALENT"]   # 인재상은 TALENT


class Claim(BaseModel):
    claim_id: str                       # CL-001
    source_doc: Literal["resume", "cover_letter"]
    text: str                           # 원문 그대로 (코드가 원문 포함 여부 검사)
    types: list[Literal["METRIC", "ROLE", "TECH", "PROBLEM", "DECISION", "COLLAB", "MEASURE"]]


class Checkpoint(BaseModel):
    checkpoint_id: str                  # CP-001
    claim_ids: list[str]
    title: str                          # 한 줄: "검색 품질 측정 기준"
    what_to_verify: str


class RequirementLink(BaseModel):       # 공고·직무기술서 요구사항 ↔ 지원자 경험
    requirement_id: str
    claim_ids: list[str]                # 비어 있으면 "서류에 근거 없음"


class Analysis(BaseModel):
    requirements: list[Requirement]
    claims: list[Claim]
    checkpoints: list[Checkpoint]
    links: list[RequirementLink]


class Step(BaseModel):                  # 화면 3·6의 단계 표시
    step_id: str
    label: str
    state: Literal["PENDING", "RUNNING", "DONE"]
    detail: Optional[str] = None        # "요구사항 16개 확인"
