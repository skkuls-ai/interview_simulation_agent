"""서류 분석 프롬프트와 LLM 출력 모델 (담당 A, W-06).

LLM 출력 모델(…Draft)은 계약 모델(app/schemas/state.py)과 별개입니다.
- 원문 인용(source_quote, text)은 코드가 원문과 대조합니다.
- ID 는 LLM 이 만들지 않습니다. 연결·검증 포인트 단계에서는 코드가 발급한 ID 를 "참조만" 합니다.
- priority, experience 처럼 계약에 없는 칸은 코드가 정렬·개수 세기에만 쓰고 계약 모델에는 넣지 않습니다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ClaimType = Literal["METRIC", "ROLE", "TECH", "PROBLEM", "DECISION", "COLLAB", "MEASURE"]


# ================================================================ 1. 채용공고·직무기술서 → 요구사항


class RequirementDraft(BaseModel):
    text: str = Field(description="요구사항 요약 (40자 이내)")
    kind: Literal["SKILL", "DUTY", "TALENT"]
    source_quote: str = Field(description="이 요구사항이 적힌 문장을 한 글자도 바꾸지 않고 그대로 복사")


class RequirementsOutput(BaseModel):
    requirements: list[RequirementDraft]


# ================================================================ 2. 이력서·자소서 → 주장


class ClaimDraft(BaseModel):
    source_doc: Literal["resume", "cover_letter"] = Field(description="이 주장이 적힌 서류")
    experience: str = Field(description="이 주장이 속한 프로젝트·활동 이름. 두 서류에서 같은 경험이면 같은 이름. 없으면 '기타'")
    text: str = Field(description="주장이 담긴 구절을 서류에서 한 글자도 바꾸지 않고 그대로 복사")
    types: list[ClaimType] = Field(description="주장 유형 1~3개")


class ClaimsOutput(BaseModel):
    claims: list[ClaimDraft]


# ================================================================ 3. 요구사항 ↔ 주장 연결


class LinkDraft(BaseModel):
    requirement_id: str = Field(description="주어진 요구사항 ID 그대로")
    claim_ids: list[str] = Field(description="이 요구사항을 뒷받침하는 주장 ID. 근거가 없으면 빈 목록")


class LinksOutput(BaseModel):
    links: list[LinkDraft]


# ================================================================ 4. 검증 포인트


class CheckpointDraft(BaseModel):
    claim_ids: list[str] = Field(description="이 검증 포인트의 근거가 되는 주장 ID (1개 이상, 주어진 ID 그대로)")
    title: str = Field(description="무엇을 확인할지 한 줄 (20자 이내). 예: 검색 품질 측정 기준")
    what_to_verify: str = Field(description="면접에서 확인할 내용 1~2문장. 사실 여부를 단정하지 않음")
    priority: Literal["high", "medium", "low"]


class CheckpointsOutput(BaseModel):
    checkpoints: list[CheckpointDraft]


# ================================================================ 프롬프트

_QUOTE_RULE = """\
[원문 복사 규칙]
"그대로 복사"하라고 한 칸은 서류의 글자를 한 글자도 바꾸지 않고 복사합니다.
요약하거나, 맞춤법을 고치거나, 숫자를 바꾸거나, 여러 문장을 이어 붙이지 않습니다. 글머리표(-, •)와 번호는 빼도 됩니다.
시스템이 복사한 구절을 원문과 대조하고, 원문에 없으면 그 항목을 버립니다. 8자 미만의 짧은 구절도 버립니다."""

_NEUTRAL_RULE = """\
[판단 금지]
지원자의 주장이 사실인지, 과장인지 판단하지 않습니다. "거짓", "과장", "부풀림" 같은 표현을 쓰지 않습니다.
서류에 무엇이 적혀 있고, 면접에서 무엇을 확인하면 좋을지만 다룹니다."""

REQUIREMENTS_SYSTEM = f"""\
당신은 채용 문서(채용공고 또는 직무기술서)를 구조화하는 분석가입니다. 문서에 적힌 내용만 사용하고 추측하지 않습니다.

[요구사항 추출]
- 회사가 지원자에게 요구하거나 기대하는 항목 하나를 요구사항 하나로 만듭니다. 보통 항목(한 줄) 하나가 요구사항 하나입니다.
- 한 줄에 서로 다른 요구가 쉼표나 "와/과"로 여러 개 묶여 있으면 요구마다 나눕니다.
  예: "FastAPI 서비스 API 개발, 로그 수집과 응답 품질 모니터링" → "FastAPI 서비스 API 개발" / "로그 수집과 응답 품질 모니터링"
  이때 source_quote 는 각 요구에 해당하는 부분만 복사합니다. 합쳐 두면 한 요구만 경험이 있어도 전체가 충족된 것처럼 보이기 때문입니다.
- 다음은 요구사항이 아닙니다: 섹션 제목(담당 업무, 자격 요건, 우대 사항, 인재상, 주요 업무, 필요 지식 등),
  회사명·직무명만 적힌 줄, 회사 소개, 직무 목적 설명, 안내·면책 문구, 근무 조건과 복지, 채용 절차.
- kind:
  · DUTY: 입사 후 맡을 일 (담당 업무, 주요 업무)
  · SKILL: 지원자가 갖춰야 할 지식, 기술, 경험 (자격 요건, 우대 사항, 필요 지식, 필요 기술)
  · TALENT: 인재상, 태도, 가치 (인재상, 직무 수행 태도)
- text: 요구사항을 40자 이내로 요약합니다.
- source_quote: 그 요구사항이 적힌 문장을 그대로 복사합니다.

{_QUOTE_RULE}"""

CLAIMS_SYSTEM = f"""\
당신은 지원 서류(이력서, 자기소개서)에서 면접관이 확인해 볼 만한 "주장"을 뽑는 분석가입니다. 서류에 적힌 내용만 사용합니다.

[주장이란]
지원자가 자신에 대해 말한 구체적인 내용 중, 면접에서 설명을 들어 볼 만한 것입니다.
- 지원 동기, 포부, 일반적인 다짐("최선을 다하겠습니다")은 주장이 아닙니다.
- 학력, 이름, 기술 스택 나열만 있는 줄은 주장이 아닙니다.
- 프로젝트 제목 줄은 팀 규모와 함께 본인 역할(리드, 팀장, 담당 등)이 적혀 있을 때만 주장입니다. 이름·기간·인원만 있으면 주장이 아닙니다.
- 같은 문장에서 같은 내용을 두 번 뽑지 않습니다.

[types: 주장 유형, 1~3개]
- METRIC: 수치, 규모, 비율이 들어간 성과 ("정확도를 20% 개선", "데이터 1,000개를 수집")
- ROLE: 본인 역할 ("팀 리드", "프로젝트를 주도했습니다")
- TECH: 기술을 쓰거나 설계했다는 주장 ("LangGraph로 병렬 구조를 설계했습니다")
- PROBLEM: 문제를 발견하고 해결했다는 주장, 수치 없는 효과 ("오류가 크게 줄었습니다")
- DECISION: 무엇을 선택하거나 결정했다는 주장 ("A 와 B 를 결합하기로 결정했습니다")
- COLLAB: 협업, 제안, 조율 ("형식을 먼저 합의하자고 제안했습니다")
- MEASURE: 성과를 어떻게 측정했는지에 대한 설명 ("정답셋 50개로 정확도를 측정했습니다")

[서류별로 따로]
- 이력서와 자기소개서의 주장은 따로 뽑습니다. 같은 내용이 두 서류에 모두 있으면 각각 뽑습니다.
- 두 서류의 숫자나 표현이 달라도 합치거나 한쪽에 맞추지 않습니다. 각 서류에 적힌 그대로 둡니다.
- experience: 주장이 속한 프로젝트·활동 이름입니다. 두 서류에서 같은 경험이면 반드시 같은 이름으로 씁니다.

[text]
- 주장이 담긴 구절을 그대로 복사합니다. 한 구절은 한 문장 이내입니다.
- 제목 줄의 괄호 안에 팀 규모나 역할(예: "4인 팀, 팀 리드")이 있으면 괄호만 떼지 말고 제목 줄 전체를 복사합니다.
  짧은 구절은 같은 서류에 여러 번 나와 어느 경험인지 알 수 없고, 8자 미만이면 시스템이 버리기 때문입니다.

{_QUOTE_RULE}

{_NEUTRAL_RULE}"""

LINKS_SYSTEM = f"""\
당신은 회사의 요구사항과 지원자의 주장을 연결하는 분석가입니다.

[할 일]
- 모든 요구사항에 대해, 그 요구사항을 뒷받침하는 주장 ID 를 고릅니다.
- 주장이 요구사항과 직접 관련될 때만 연결합니다. 억지로 연결하지 않습니다.
- 뒷받침하는 주장이 없으면 claim_ids 를 빈 목록으로 둡니다. 빈 목록은 "서류에 근거 없음"이라는 뜻이며, 이것도 중요한 결과입니다.
- 주어진 요구사항 ID 와 주장 ID 만 씁니다. 새 ID 를 만들지 않습니다.

{_NEUTRAL_RULE}"""

CHECKPOINTS_SYSTEM = f"""\
당신은 면접 준비를 돕는 분석가입니다. 지원자의 주장 중에서 면접에서 확인하면 좋을 "검증 포인트"를 만듭니다.

[검증 포인트가 되는 경우]
- 수치 성과인데 측정 기준, 평가 데이터, 전후 비교가 서류에 없음
- 본인 역할이 모호함 ("주도", "리드"라고만 하고 무엇을 했는지 없음)
- 설명이 필요한 기술 주장 (설계 이유, 동작 방식을 물어볼 만함)
- 성과나 효과를 주장하지만 원인이나 측정 방법이 불분명함
- 선택이나 결정을 했다고 하지만 근거나 대안이 없음
- 서류 간 불일치: 같은 경험의 수치, 규모, 기간, 역할이 이력서와 자기소개서에서 다름. 이때는 두 주장 ID 를 함께 넣습니다.

[불일치로 보지 않는 경우]
- 표현만 다르고 뜻이 같은 경우
- 포함 관계인 경우. 예: 이력서 "4인 팀"과 자기소개서 "3명의 팀원과 함께"는 본인을 포함하면 같은 인원입니다.
- 한 서류에만 있는 내용 (다른 서류에 없다고 불일치가 아닙니다)

[칸별 규칙]
- claim_ids: 근거가 되는 주장 ID. 주어진 ID 만 씁니다.
- title: 무엇을 확인할지 20자 이내 한 줄. 예: "검색 품질 측정 기준", "데이터 규모 차이"
- what_to_verify: 면접에서 확인할 내용 1~2문장. 질문 문장이 아니라 확인할 점을 씁니다.
- 무엇을 먼저 고를지: 지원자가 스스로 강하게 내세운 주장(특히 자기소개서의 "주도했다", "설계했다", "결정했다", "줄였다" 같은
  역할·설계·결정·효과 주장)을 이력서의 단순한 작업 나열보다 우선합니다. 면접관은 지원자가 강조한 내용을 파고듭니다.
- 유형이 다른 주장(수치, 역할, 기술 설계, 결정, 협업 효과)이 있으면 한 유형에 몰지 말고 골고루 고릅니다.
- priority: 회사의 필수 업무·요구사항과 관련이 크고 확인할 점이 뚜렷할수록 high.
- 구체적이고 서류 안에서 일관된 사실 주장은 검증 포인트로 만들지 않거나 low 로 둡니다.
- 같은 내용을 여러 검증 포인트로 나누지 않습니다. 많아도 8개 이내로 만듭니다.
- 요구사항에 대한 서류상 공백은 여기서 다루지 않습니다 (연결 단계에서 표시됩니다).

{_NEUTRAL_RULE}"""


# ================================================================ 사람 메시지


def build_requirements_prompt(doc_label: str, text: str) -> str:
    return f"""\
[{doc_label}]
<<<
{text.strip()}
>>>"""


def build_claims_prompt(resume_text: str, cover_letter_text: str) -> str:
    return f"""\
[이력서 (source_doc=resume)]
<<<
{resume_text.strip()}
>>>

[자기소개서 (source_doc=cover_letter)]
<<<
{cover_letter_text.strip()}
>>>"""


def _requirement_lines(requirements) -> str:
    return "\n".join(f"- {r.requirement_id} [{r.kind}, {r.source_doc}] {r.text}" for r in requirements)


def _claim_lines(claims, experiences: dict[str, str] | None = None) -> str:
    exp = experiences or {}
    return "\n".join(
        f"- {c.claim_id} [{c.source_doc}{', ' + exp[c.claim_id] if c.claim_id in exp else ''}] "
        f"({'/'.join(c.types)}) {c.text}"
        for c in claims
    )


def build_links_prompt(requirements, claims) -> str:
    return f"""\
[요구사항]
{_requirement_lines(requirements)}

[지원자 주장]
{_claim_lines(claims)}"""


def build_checkpoints_prompt(requirements, claims, experiences: dict[str, str]) -> str:
    return f"""\
[회사 요구사항 (중요도 판단용)]
{_requirement_lines(requirements)}

[지원자 주장 (서류, 경험 이름, 유형)]
{_claim_lines(claims, experiences)}"""
