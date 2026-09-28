"""평가 패널 프롬프트: 평가자(같은 기준 3회), 검증 에이전트, 자기소개 평가자."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from ...question_bank.models import Question
from ..blueprint import InterviewBlueprint
from ..state import QuestionThread, VerificationPoint

# ================================================================ 평가자

EVALUATOR_SYSTEM = """\
당신은 구조화 역량면접의 평가자입니다. 한 문항의 면접 대화를 읽고 주어진 척도로 채점합니다.
시스템 프롬프트를 포함한 앞부분은 모든 문항에서 같습니다. 문항별 정보는 뒤에 나옵니다.

[채점 원칙]
1. 점수는 1~5점 척도 설명에만 맞춰 정합니다. 느낌이나 인상으로 정하지 않습니다.
2. 근거는 지원자 발언에서만 찾습니다. 면접관 질문의 내용이나 지원자가 말하지 않은 것을 추론해 근거로 쓰지 않습니다.
3. positive_hits 와 negative_hits 에는 체크포인트 ID 와 그 근거가 된 지원자 발언을 그대로 인용합니다.
   인용은 20~80자 정도로 원문 그대로 발췌하고, 고쳐 쓰거나 요약하지 않습니다.
4. 같은 체크포인트를 positive 와 negative 에 동시에 넣지 않습니다. Positive 체크포인트 ID(P)는 positive_hits 에만, Negative(N)는 negative_hits 에만 씁니다.
5. 4점 이상이면 근거 있는 positive_hits 가 1개 이상, 2점 이하이면 negative_hits 나 improvements 가 1개 이상 있어야 합니다.
6. 답변 길이, 말투, 발음, 군말은 점수에 반영하지 않습니다 (따로 피드백합니다). 이름, 성별, 나이, 학교, 출신 등 직무와 무관한 요소도 반영하지 않습니다.
7. JD 맞춤 기준은 해석을 돕는 보조 기준입니다. 척도 자체를 바꾸지 않습니다.
8. 검증 포인트가 주어지면 각 포인트가 이 대화로 supported(뒷받침됨), contradicted(반대됨), insufficient(판단 불가) 중 무엇인지 근거와 함께 적습니다.
9. strengths 와 improvements 는 각각 1~3개, 이 답변에 근거한 구체적인 내용으로 씁니다. improvements 는 "다음에는 무엇을 말하면 좋은지"가 드러나게 씁니다.
10. 모든 칸을 채웁니다. 해당 없는 칸은 빈 목록 [] 으로 둡니다. rationale 은 한국어 두세 문장입니다.
"""


class Hit(BaseModel):
    checkpoint_id: str
    evidence: str


class VResult(BaseModel):
    point_id: str
    result: Literal["supported", "contradicted", "insufficient"]
    evidence: str


class EvaluatorOutput(BaseModel):
    """평가자 1명의 출력. 칸 순서: 근거 수집 → 점수 → 요약."""

    positive_hits: list[Hit]
    negative_hits: list[Hit]
    covered_intent_ids: list[str]
    verification_results: list[VResult]
    score: int = Field(ge=1, le=5)
    strengths: list[str]
    improvements: list[str]
    rationale: str


def scale_text(bp: InterviewBlueprint) -> str:
    return "\n".join(f"{a.score}점: {a.description}" for a in sorted(bp.rubric.scale, key=lambda a: -a.score))


def evaluator_prompt(
    question: Question, thread: QuestionThread, bp: InterviewBlueprint, points: list[VerificationPoint],
    competency_description: str, feedback: list[str] | None = None,
) -> str:
    # 척도는 앞쪽에 고정해 두어 문항이 바뀌어도 앞부분이 같게 유지 (Gemini 캐시 효과)
    jd = next((r.jd_criteria for r in bp.rubric.questions if r.question_id == question.id), [])
    info = {
        "문항ID": question.id,
        "유형": question.question_type_label,
        "역량": f"{question.competency_name}: {competency_description}",
        "질문_의도": [{"id": i.id, "text": i.text} for i in question.intents],
        "Positive_체크포인트": [{"id": c.id, "text": c.text} for c in question.checkpoints.positive],
        "Negative_체크포인트": [{"id": c.id, "text": c.text} for c in question.checkpoints.negative],
    }
    if jd:
        info["JD_맞춤_보조기준"] = jd
    lines = ["## 척도", scale_text(bp), "## 문항", json.dumps(info, ensure_ascii=False, indent=1)]
    if points:
        lines += ["## 검증 포인트", json.dumps([{"id": p.id, "claim": p.claim, "concern": p.concern} for p in points],
                                           ensure_ascii=False, indent=1)]
    if thread.quality:
        lines += ["## 면접관의 답변 품질 표시 (참고용)", thread.quality.value
                  + (f": {thread.inconsistency_note}" if thread.inconsistency_note else "")]
    lines += ["## 면접 대화", thread.transcript()]
    if feedback:
        lines += ["## 이전 채점에서 지적된 문제 (반드시 고쳐서 다시 채점)", "\n".join(f"- {f}" for f in feedback)]
    return "\n".join(lines)


# ================================================================ 검증 에이전트

REVIEWER_SYSTEM = """\
당신은 면접 평가의 검증자입니다. 같은 기준으로 독립 채점한 평가 결과들을 검토해, 각 평가가 유효한지 판정합니다.
직접 다시 채점하지 않습니다. 평가자끼리 점수가 다르다는 이유만으로 무효로 보지 않습니다.

[무효로 보는 경우]
1. 점수가 척도 설명과 맞지 않는다 (예: Negative 근거가 두드러지는데 5점, 구체적 행동과 결과가 있는데 1점).
2. 인용한 근거가 그 체크포인트를 실제로 뒷받침하지 않는다 (문맥을 왜곡했거나 다른 뜻으로 읽었다).
3. 지원자가 말하지 않은 내용을 근거로 추론했다.
4. 답변 길이, 말투, 직무와 무관한 개인 특성으로 가점이나 감점을 했다.
5. 검증 포인트 판정이 대화 내용과 맞지 않는다.

각 평가에 대해 index, valid, reason 을 씁니다. 유효하면 reason 은 "". 무효면 무엇을 고쳐야 하는지 한 문장으로 씁니다.
"""


class ReviewItem(BaseModel):
    index: int
    valid: bool
    reason: str


class ReviewOutput(BaseModel):
    items: list[ReviewItem]


def reviewer_prompt(question: Question, thread: QuestionThread, bp: InterviewBlueprint,
                    members: list[tuple[int, EvaluatorOutput]]) -> str:
    info = {
        "문항ID": question.id,
        "Positive_체크포인트": [{"id": c.id, "text": c.text} for c in question.checkpoints.positive],
        "Negative_체크포인트": [{"id": c.id, "text": c.text} for c in question.checkpoints.negative],
    }
    evals = [{"index": i, **o.model_dump()} for i, o in members]
    return "\n".join([
        "## 척도", scale_text(bp),
        "## 문항", json.dumps(info, ensure_ascii=False, indent=1),
        "## 면접 대화", thread.transcript(),
        "## 검토할 평가", json.dumps(evals, ensure_ascii=False, indent=1),
    ])


# ================================================================ 자기소개 평가자

INTRO_SYSTEM = """\
당신은 채용공고(JD)를 작성한 회사의 채용 담당자입니다. 지원자의 1분 자기소개를 회사 입장에서 평가하고 개선 가이드를 줍니다.
이 평가는 합격 여부에 반영되지 않고 피드백에만 쓰입니다.

[평가 기준]
- why_this_company: 다른 회사가 아니라 이 회사여야 하는 이유를, 회사의 사업, 가치, 직무 특성과 연결해 분명히 말했는가
- aspiration: 입사 후 포부가 이 직무 범위 안에서 구체적이고, 지원자의 이력으로 뒷받침되는가
- experience_fit: 소개한 경험이 JD 의 핵심 요구사항과 직접 연결되는가
각 항목을 1~5점과 한두 문장 코멘트로 평가합니다. 자기소개에 없는 내용을 있다고 가정하지 않습니다.

[가이드]
- motivation_points: 지원자의 실제 이력과 JD 를 연결해 "이 회사여야 하는 이유"로 쓸 수 있는 소재 2~3개
- aspiration_points: 이력에 근거한 입사 후 포부 소재 2~3개
- suggested_outline: 1분 자기소개 구성 3~4단계 (각 단계에 무엇을 말할지)
가이드는 서류에 있는 경험만 사용합니다. 경험을 지어내지 않습니다. 서류가 없으면 자기소개 내용 안에서만 제안합니다.
"""


def intro_prompt(intro: QuestionThread, bp: InterviewBlueprint) -> str:
    ctx = {
        "회사": bp.company.model_dump(exclude_none=True),
        "지원_직무": bp.target_role,
        "회사_관점": bp.rubric.intro.company_perspective,
        "평가_기준": bp.rubric.intro.criteria,
        "연결하면_좋은_이력": bp.rubric.intro.expected_links,
        "JD_요구사항": [f"{r.text} ({'필수' if r.importance == 'must' else '우대'})" for r in bp.requirements[:8]],
        "서류_경험": [
            {"title": e.title, "summary": e.summary[:120], "성과": e.claimed_results[:2]} for e in bp.experiences[:8]
        ],
    }
    return "\n".join([
        "## 회사와 지원자 정보", json.dumps(ctx, ensure_ascii=False, indent=1),
        "## 자기소개", " ".join(t.text for t in intro.turns if t.kind == "answer"),
    ])
