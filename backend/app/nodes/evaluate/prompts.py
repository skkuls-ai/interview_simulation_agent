"""평가 프롬프트와 LLM 출력 모양 (초안, 5번 작업에서 다듬음).

LLM 은 판정 후보, 이유, 인용할 문장, 조언만 쓴다. ID 발급, 인용 위치, 최종 판정 확정은 코드(rules.py)가 한다.
시선 값(delivery)은 직무 적합성, 일관성, 질문별 프롬프트에 넣지 않는다 (T-213).
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from ...schemas.state import Analysis, Answer, Question

# LLM 출력 스키마용 판정 라벨 (schemas.state.Verdict 와 같은 값)
Verdict = Literal["SUFFICIENT", "NEEDS_WORK", "INSUFFICIENT", "WITHHELD"]

# ---------------------------------------------------------------- LLM 출력 모양


class QuoteRef(BaseModel):
    question_id: str
    text: str  # 답변 받아쓰기에서 그대로 옮긴 문장. 위치는 코드가 찾음


class AdviceItem(BaseModel):
    text: str
    quotes: list[QuoteRef] = []


class AttitudeOut(BaseModel):
    advice: list[AdviceItem]


class FitOut(BaseModel):
    verdict: Verdict
    reason: str
    quotes: list[QuoteRef]
    refs: list[str]


class QuestionOut(BaseModel):
    question_id: str
    strengths: list[str]
    gaps: list[str]
    next_action: str
    extra_claim_ids: list[str] = []  # 검증 포인트 밖에서 이 답변과 관련된 주장 ID


class PerQuestionOut(BaseModel):
    items: list[QuestionOut]


Target = Literal["attitude", "job_fit", "consistency", "per_question"]


class ReviewItem(BaseModel):
    target: Target
    valid: bool
    reason: str


class ReviewOut(BaseModel):
    items: list[ReviewItem]


# ---------------------------------------------------------------- 공통 원칙

COMMON = """\
[공통 원칙]
1. 근거는 지원자 답변(받아쓰기)에서만 찾는다. 면접관 질문이나 서류 내용을 지원자가 말한 것처럼 쓰지 않는다.
2. 인용(quotes.text)은 받아쓰기에서 글자 그대로 옮긴다. 고쳐 쓰거나 요약하지 않는다. "어", "음" 같은 군말도 그대로 둔다.
   판정이나 조언에 필요한 부분만 짧게 옮긴다 (8자 이상, 한 문장을 넘지 않게, 보통 15~50자). 문장 전체나 여러 문장을 통째로 옮기지 않는다.
3. 받아쓰기에는 인식 오류가 있을 수 있고, 숫자가 "3개"와 "세 개"처럼 다르게 적힐 수 있다. 같은 값으로 본다.
4. 합격 가능성, 채용 점수, 상위 몇 %, 자신감, 진실성, 긴장, 불안, 성격을 판단하거나 언급하지 않는다.
5. 서류의 주장이 사실인지 판단하지 않는다. 서류와 답변이 일치하는지만 본다.
6. 한국어 존댓말로, 지원자에게 직접 말하듯 짧고 구체적으로 쓴다.
7. 지원자가 읽는 문장(reason, advice, strengths, gaps, next_action)에는 RQ-, CL-, CP-, Q- 같은 ID 를 쓰지 않는다.
   ID 는 refs, quotes.question_id, extra_claim_ids 칸에만 쓴다. 질문을 가리킬 때는 "마지막 질문", "기술 질문"처럼 쓴다.
8. 모르는 것, 해 보지 않은 것, 한계를 솔직히 말한 부분을 빼거나 숨기거나 돌려 말하라고 조언하지 않는다.
   그 말은 그대로 두고, 그 위에 무엇을 더하면 되는지(배운 점, 대신 해 본 것, 앞으로의 계획)를 쓴다.
9. 서류와 답변이 다를 때 "서류에 맞춰 말하라"고 하지 않는다. 실제 사실을 확인해 틀린 쪽(서류든 답변이든)을 바로잡으라고 쓴다.
"""

VERDICTS = """\
[판정]
- SUFFICIENT: 기준을 구체적 근거와 함께 충족
- NEEDS_WORK: 일부 충족, 빠지거나 모호한 부분이 있음
- INSUFFICIENT: 기준을 거의 충족하지 못함
- WITHHELD: 판단할 근거 답변이 부족함
판정에는 인용이 1개 이상 있어야 한다 (WITHHELD 제외).
"""

ATTITUDE_SYSTEM = COMMON + """
당신은 면접 코치입니다. 지원자의 말투와 시간 사용을 보고 조언 1~3개를 씁니다. 판정이나 점수는 쓰지 않습니다.
- 조언 하나는 두 문장 이내: 무엇이 보였는지 한 문장, 어떻게 바꾸면 되는지 한 문장.
- 측정값(분당 어절 수, 군말 횟수, 시간 초과, 시선)은 코드가 계산한 값이다. 숫자를 바꾸지 않는다.
- 말투 조언(문장 끝 흐리기, 반복 표현 등)에는 그 말투가 드러난 인용을 붙인다.
- 시선 값은 참고 측정값이다. 시선으로 태도나 성향을 판단하지 않는다.
"""

JOB_FIT_SYSTEM = COMMON + VERDICTS + """
당신은 채용 담당자입니다. 면접 답변 전체가 채용공고와 직무기술서의 요구사항을 얼마나 뒷받침하는지 판정합니다.
- refs 에는 판정의 근거가 된 요구사항 ID(RQ-)만 넣는다. 목록에 없는 ID 는 쓰지 않는다.
- reason 은 두세 문장. 잘 뒷받침된 요구사항과 부족한 요구사항을 함께 쓴다.
"""

CONSISTENCY_SYSTEM = COMMON + VERDICTS + """
당신은 채용 담당자입니다. 면접 답변이 이력서와 자기소개서의 주장과 일치하는지 판정합니다.
- 수치, 역할, 기간, 규모가 서류와 다르게 말한 부분을 찾는다. 서류에 없는 새 내용은 불일치로 보지 않는다.
- refs 에는 비교한 주장 ID(CL-)만 넣는다. 목록에 없는 ID 는 쓰지 않는다.
- 어긋난 부분이 있으면 reason 에 무엇과 무엇이 다른지 쓰고, 두 문장을 모두 인용한다.
"""

PER_QUESTION_SYSTEM = COMMON + """
당신은 면접 코치입니다. 질문마다 잘한 점(strengths) 1~2개, 부족한 점(gaps) 1~2개, 다음 연습 행동(next_action) 1문장을 씁니다.
- strengths 와 gaps 는 항목마다 한 문장.
- next_action 은 무엇을 준비하거나 말하면 되는지 구체적으로 쓴다. 다섯 질문의 문장 끝맺음이 같은 표현으로 반복되지 않게 한다
  ("연습해 보세요"만 반복하지 말고 "정리해 두세요", "덧붙여 말해 보세요", "한 문장으로 준비해 두세요"처럼 행동에 맞게).
- 질문의 평가 기준(criteria)과 연결된 검증 포인트를 기준으로 본다.
- 기술 이해는 이 질문별 피드백에서 다룬다.
- 답변 내용(상황, 본인 역할, 행동, 수치, 결과, 기술 설명)만 다룬다. 어조, 말투, 확신, 목소리 같은 전달 방식은 쓰지 않는다
  (전달 방식은 태도 조언이 따로 다룬다). 예: "확신 있는 어조로 말해 보세요"(X) → "직접 결정한 내용을 한 문장으로 덧붙여 보세요"(O).
- extra_claim_ids 에는 검증 포인트 밖에서 이 답변과 직접 관련된 주장 ID 만 넣는다. 없으면 빈 목록.
- 주어진 질문 ID 마다 정확히 하나씩 쓴다.
"""

REVIEWER_SYSTEM = """\
당신은 면접 피드백의 검증자입니다. 다른 평가자가 쓴 직무 적합성, 답변 일관성 판정이 유효한지 판정합니다. 직접 다시 평가하지 않습니다.

[무효로 보는 경우]
1. 판정이 인용과 이유에 맞지 않는다 (근거가 분명한데 INSUFFICIENT, 부족한데 SUFFICIENT).
2. 인용이 그 판정이나 조언을 실제로 뒷받침하지 않는다 (문맥을 왜곡했거나 다른 뜻으로 읽었다).
3. 지원자가 말하지 않은 내용을 근거로 추론했다.
4. 말투, 답변 길이, 시선, 개인 특성으로 직무 적합성이나 일관성 판정을 바꿨다.
5. 서류에 없는 새 내용을 불일치로 판정했다.

검토할 항목마다 target, valid, reason 을 쓴다. 유효하면 reason 은 "". 무효면 무엇을 고쳐야 하는지 한 문장으로 쓴다.
"""

# ---------------------------------------------------------------- 입력 조립


def _v(x):
    """Enum 이면 값, 아니면 그대로."""
    return getattr(x, "value", x)


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


def _answers(questions: list[Question], answers: dict[str, Answer], with_criteria: bool = False) -> list[dict]:
    rows = []
    for q in questions:
        a = answers.get(q.question_id)
        row = {"question_id": q.question_id, "type": _v(q.type), "question": q.text, "answer": a.transcript}
        if with_criteria:
            row["criteria"] = q.criteria
            row["checkpoint_ids"] = q.checkpoint_ids
        rows.append(row)
    return rows


def _feedback(issues: list[str] | None) -> list[str]:
    if not issues:
        return []
    return ["## 이전 결과에서 지적된 문제 (반드시 고쳐서 다시 작성)", "\n".join(f"- {i}" for i in issues)]


def attitude_prompt(questions, answers, metrics: dict, issues=None) -> str:
    return "\n".join([
        "## 측정값 (코드 계산)", _dump(metrics),
        "## 질문과 답변 받아쓰기", _dump(_answers(questions, answers)),
        *_feedback(issues),
    ])


def job_fit_prompt(questions, answers, analysis: Analysis, issues=None) -> str:
    reqs = [{"id": r.requirement_id, "kind": _v(r.kind), "text": r.text} for r in analysis.requirements]
    return "\n".join([
        "## 요구사항 (채용공고, 직무기술서)", _dump(reqs),
        "## 질문과 답변 받아쓰기", _dump(_answers(questions, answers)),
        *_feedback(issues),
    ])


def consistency_prompt(questions, answers, analysis: Analysis, issues=None) -> str:
    claims = [{"id": c.claim_id, "source": _v(c.source_doc), "text": c.text} for c in analysis.claims]
    return "\n".join([
        "## 서류의 주장 (이력서, 자기소개서)", _dump(claims),
        "## 질문과 답변 받아쓰기", _dump(_answers(questions, answers)),
        *_feedback(issues),
    ])


def per_question_prompt(questions, answers, analysis: Analysis, issues=None) -> str:
    cps = [{"id": c.checkpoint_id, "title": c.title, "what_to_verify": c.what_to_verify, "claim_ids": c.claim_ids}
           for c in analysis.checkpoints]
    claims = [{"id": c.claim_id, "text": c.text} for c in analysis.claims]
    return "\n".join([
        "## 검증 포인트", _dump(cps),
        "## 서류의 주장", _dump(claims),
        "## 질문, 평가 기준, 답변 받아쓰기", _dump(_answers(questions, answers, with_criteria=True)),
        *_feedback(issues),
    ])


def reviewer_prompt(questions, answers, outputs: dict[str, BaseModel]) -> str:
    return "\n".join([
        "## 질문과 답변 받아쓰기", _dump(_answers(questions, answers)),
        "## 검토할 피드백", _dump({k: v.model_dump() for k, v in outputs.items()}),
    ])
