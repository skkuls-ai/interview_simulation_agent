"""분석 에이전트 프롬프트와 LLM 출력 모델 (JD 분석, 경험 분석).

LLM 출력 모델은 Blueprint 모델과 별개입니다. 원문 인용(source_quote)처럼 코드 검증에만 쓰는 칸이 있고,
ID 는 LLM 이 만들지 않습니다. llm_analysis_agents.py 가 검증을 거쳐 Blueprint 모델로 바꿉니다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# (code, 이름, 설명)
Competency = tuple[str, str, str]


# ================================================================ 출력 모델


class JDRequirementDraft(BaseModel):
    text: str = Field(description="요구사항 요약 (40자 이내)")
    kind: Literal["duty", "skill", "experience", "trait", "culture"]
    importance: Literal["must", "preferred"]
    competency_codes: list[str] = Field(description="역량 목록의 code 중 직접 관련된 것 0~3개")
    source_quote: str = Field(description="이 요구사항이 적힌 공고 문장을 한 글자도 바꾸지 않고 그대로 복사")


class JDAnalysisOutput(BaseModel):
    company_name: str | None = Field(description="공고에 적힌 회사 이름 그대로. 없으면 null")
    role_title: str | None = Field(description="공고에 적힌 직무 이름 그대로. 없으면 null")
    mission_or_values: list[str] = Field(description="공고에 드러난 회사의 지향점이나 인재상 (최대 5개, 짧게)")
    business_summary: str | None = Field(description="회사가 하는 일 한 문장. 공고에 없으면 null")
    requirements: list[JDRequirementDraft]


class ExperienceDraft(BaseModel):
    source: Literal["resume", "cover_letter"] = Field(description="이 경험이 적힌 서류")
    title: str = Field(description="프로젝트나 활동 이름. 서류에 이름이 있으면 그대로")
    organization: str | None = Field(description="소속이나 기관. 서류에 없으면 null")
    period: str | None = Field(description="기간. 서류에 없으면 null")
    summary: str = Field(description="서류에 적힌 사실만으로 쓴 1~2문장")
    claimed_results: list[str] = Field(
        description="확인이 필요한 주장(성과, 수치, 규모, 본인 역할)이 담긴 구절을 서류에서 그대로 복사한 것"
    )
    competency_codes: list[str] = Field(description="역량 목록의 code 중 이 경험에서 드러난 것 0~3개")
    source_quote: str = Field(description="이 경험을 가리키는 서류 문장(보통 제목 줄이나 첫 문장)을 그대로 복사")


class ExperienceAnalysisOutput(BaseModel):
    experiences: list[ExperienceDraft]


# ================================================================ 프롬프트

_QUOTE_RULE = """\
[원문 복사 규칙]
source_quote, claimed_results 처럼 "그대로 복사"하라고 한 칸은 서류의 글자를 한 글자도 바꾸지 않고 복사합니다.
요약하거나, 맞춤법을 고치거나, 숫자를 바꾸거나, 여러 문장을 이어 붙이지 않습니다. 글머리표(-, •)와 번호는 빼도 됩니다.
시스템이 복사한 구절을 원문과 대조하고, 원문에 없으면 그 항목을 버립니다."""

JD_SYSTEM = f"""\
당신은 채용공고를 구조화하는 분석가입니다. 공고에 적힌 내용만 사용하고 추측하지 않습니다.

[요구사항 추출]
- 회사가 지원자에게 요구하거나 기대하는 항목 하나를 요구사항 하나로 만듭니다. 보통 공고의 항목(한 줄) 하나가 요구사항 하나입니다.
- 다음은 요구사항이 아닙니다: 섹션 제목(담당 업무, 자격 요건, 우대 사항, 인재상 등), 회사명이나 직무명만 적힌 줄,
  회사 소개 문장, 안내 문구나 면책 문구, 근무 조건과 복지, 채용 절차.
- kind: duty(담당 업무), skill(기술, 도구), experience(경험 요건), trait(태도, 인재상), culture(조직 문화, 가치)
- importance: 담당 업무, 자격 요건, 필수 요건은 must. 우대 사항, 가산점, 인재상은 preferred.
- text: 요구사항을 40자 이내로 요약합니다.
- source_quote: 그 요구사항이 적힌 공고 문장을 그대로 복사합니다.
- competency_codes: 역량 목록의 code 중 이 요구사항과 직접 관련된 것만 0~3개 고릅니다. 목록에 없는 code 를 만들지 않고, 억지로 연결하지 않습니다.

[회사 정보]
- company_name, role_title 은 공고에 적힌 그대로 씁니다. 없으면 null 입니다.
- mission_or_values 는 공고에 드러난 회사의 지향점이나 인재상을 짧게 최대 5개 씁니다.

{_QUOTE_RULE}"""

EXPERIENCE_SYSTEM = f"""\
당신은 지원 서류(이력서, 자기소개서)에서 경험을 추출하는 분석가입니다. 서류에 적힌 내용만 사용하고 추측하거나 보태지 않습니다.
지원자를 평가하거나 주장이 사실인지 판단하지 않습니다. 무엇이 적혀 있는지만 정리합니다.

[경험 단위]
- 프로젝트, 근무, 인턴, 교육 중 수행한 과제, 대외활동처럼 지원자가 실제로 무언가를 한 단위를 경험 하나로 만듭니다.
- 다음은 경험이 아닙니다: 이름과 연락처, 학력만 적힌 줄, 기술 스택 나열, 자격증 목록, 지원 동기나 포부만 담긴 문장.

[서류별로 따로 추출]
- 이력서와 자기소개서는 따로 추출합니다. 같은 프로젝트가 두 서류에 모두 나오면 경험을 두 개 만들고(source 가 다름) title 은 같게 씁니다.
- 두 서류의 내용을 합치거나, 한쪽 서류의 숫자나 표현에 맞추지 않습니다. 서류끼리 다른 부분이 있으면 각 서류에 적힌 그대로 둡니다.

[칸별 규칙]
- source: 그 경험이 적힌 서류 (resume 또는 cover_letter)
- title: 프로젝트나 활동 이름. 서류에 이름이 있으면 그대로 씁니다.
- organization, period: 서류에 적혀 있을 때만 씁니다. 없으면 null 입니다.
- summary: 그 서류에 적힌 사실만으로 1~2문장.
- claimed_results: 면접에서 확인이 필요한 주장이 담긴 구절을 그대로 복사합니다. 한 구절은 한 문장 이내입니다.
  · 성과와 효과: "처리 시간을 40% 단축했습니다", "오류가 크게 줄었습니다"
  · 수치와 규모: "데이터 1,000개를 수집해", "3명의 팀원과 함께"
  · 본인 역할: "팀 리드", "프로젝트를 주도했습니다", "구조를 설계했습니다"
  · 판단이나 결정: "A 와 B 를 결합하기로 결정했습니다"
  제목 줄의 괄호 안에 팀 규모나 역할(예: "4인 팀, 팀 리드")이 있으면 괄호만 떼지 말고 제목 줄 전체를 복사합니다.
  짧은 구절은 같은 서류에 여러 번 나와 어느 경험인지 알 수 없고, 8자 미만 구절은 시스템이 버리기 때문입니다.
  해당하는 주장이 없으면 빈 목록입니다.
- competency_codes: 역량 목록의 code 중 이 경험에서 드러난 것만 0~3개. 목록에 없는 code 를 만들지 않습니다.
- source_quote: 이 경험을 가리키는 문장(보통 제목 줄이나 첫 문장)을 그대로 복사합니다.

{_QUOTE_RULE}"""


def _competency_block(competencies: list[Competency]) -> str:
    return "\n".join(f"- {code}: {name} ({desc})" for code, name, desc in competencies)


def build_jd_prompt(jd_text: str, competencies: list[Competency]) -> str:
    return f"""\
[역량 목록]
{_competency_block(competencies)}

[채용공고]
<<<
{jd_text.strip()}
>>>"""


def build_experience_prompt(
    resume_text: str | None, cover_letter_text: str | None, competencies: list[Competency]
) -> str:
    resume = (resume_text or "").strip() or "(제출하지 않음)"
    cover = (cover_letter_text or "").strip() or "(제출하지 않음)"
    return f"""\
[역량 목록]
{_competency_block(competencies)}

[이력서 (source=resume)]
<<<
{resume}
>>>

[자기소개서 (source=cover_letter)]
<<<
{cover}
>>>"""
