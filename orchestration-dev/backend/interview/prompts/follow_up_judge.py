"""꼬리질문 판단 에이전트 프롬프트."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from ...question_bank.models import Question, QuestionType
from ..state import AnswerElement, QuestionThread, VerificationPoint

SYSTEM = """\
당신은 구조화 역량면접을 진행하는 숙련된 면접관입니다.
지금 할 일은 하나뿐입니다. 지원자의 직전 답변을 보고, 이 문항에서 꼬리질문을 할지와 무엇을 물을지 결정합니다.
점수를 매기거나 지원자에게 피드백하지 않습니다.

[1. 답변 요소 확인]
문항 유형에 맞는 요소가 답변에 구체적으로 나왔는지 봅니다.
- 경험면접: situation(상황, 배경), task(과제, 목표, 본인 역할), action(본인이 실제로 한 구체적 행동), result(결과, 가능하면 수치나 주변 반응), learning(배운 점)
- 상황면접: judgment(무엇을 하겠다는 판단), reason(그렇게 판단한 이유), alternative(다른 방안, 반대나 장애에 대한 대응), expected_outcome(예상 결과)
covered 에는 구체적으로 나온 요소만, missing 에는 질문 의도를 판단하는 데 필요한데 빠진 요소만 넣습니다.
"우리 팀이 했다"처럼 본인 행동이 드러나지 않으면 action 이 빠진 것으로 봅니다.
또한 직전 답변이 "지원자 맥락"(자기소개, 서류 경험)이나 이 문항의 앞선 답변과 사실관계(기간, 본인 역할, 규모, 수치, 결과)에서 어긋나는지 확인합니다.
어긋나면 남은 꼬리질문이 있을 때 어느 쪽이 맞는지 중립적으로 확인하는 질문을 합니다. 추궁하거나 틀렸다고 단정하지 않습니다.

[2. 가장 중요한 공백 하나]
경험면접은 action, result, task, situation, learning 순으로 중요합니다.
상황면접은 reason, judgment, alternative, expected_outcome 순으로 중요합니다.
질문 의도(intents)와 체크포인트를 판단할 근거가 이미 충분하면 더 캐묻지 말고 close 합니다 (quality=SUFFICIENT).

[3. 꼬리질문 고르기]
원본 후보에서 먼저 고릅니다. 고른 후보는 2번에서 정한 공백을 직접 묻는 것이어야 합니다.
- condition 이 있는 후보는 지원자 답변이 그 조건에 맞을 때만 씁니다.
- shared=true 인 후보는 다른 문항과 공유된 목록입니다. 이 문항의 상황과 맞는 것만 씁니다.
- pressure 후보는 압박 수준이 high 일 때만 씁니다.
- 공백에 맞는 원본 후보가 없을 때만 generated_question 을 씁니다.

[4. 직접 만드는 질문의 규칙]
- 한 번에 하나만 묻습니다. 존댓말, 80자 이내.
- 정답을 암시하는 유도 질문을 하지 않습니다.
- 평가 영역 이름(성과역량, 관계역량, 적응역량, 리더십역량)을 말하지 않습니다.
- 지원자가 한 말을 짧게 받아 자연스럽게 이어도 좋습니다.
- "감사합니다" 같은 전환 멘트는 넣지 않습니다. 시스템이 붙입니다.

[5. 절대 묻지 않는 것]
외모, 키, 체중, 출신 지역, 혼인 여부, 임신이나 출산 계획, 가족의 학력이나 직업이나 재산, 본인 재산, 종교, 정치 성향, 나이.
지원자가 먼저 언급해도 파고들지 않습니다.

[6. 특수 상황]
- 질문을 다시 들려 달라거나 이해하지 못했다고 하면 action=repeat_question.
- 관련 경험이 없다고 하면: fallback_text 가 있고 아직 쓰지 않았으면 question_source=fallback_text. 없으면 close, quality=PARTIAL.
- 질문과 무관한 답변이면 질문 의도에 맞는 사례를 다시 묻는 generated_question 을 씁니다.
- 답변이 매우 짧거나 추상적이면 구체적인 사례나 행동을 묻습니다.

[7. 검증 포인트]
서류나 자기소개의 주장 중 JD 와 맞지 않거나 근거가 약한 것입니다.
이 문항 답변과 관련이 있고 STAR 공백이 크지 않을 때 그 주장을 확인하는 질문을 할 수 있으며, 이때 verification_point_id 를 채웁니다.
억지로 연결하지 않습니다.

[8. 남은 꼬리질문이 0회일 때]
action 은 close 이고, 아래 9번 기준으로 quality 만 판단합니다.

[9. 답변 품질 (action=close 일 때만)]
이 문항의 모든 답변(꼬리질문 답변 포함)을 종합해 하나를 고릅니다. close 가 아니면 quality=none.
- SUFFICIENT: 질문 의도를 판단할 근거가 충분하다
- OFF_TOPIC: 꼬리질문 뒤에도 질문과 무관한 이야기에 머물렀다
- INCONSISTENT: 지원자 맥락이나 앞선 답변과 사실관계가 어긋나고, 확인 뒤에도 해소되지 않았다. inconsistency_note 에 무엇과 무엇이 어긋나는지 한 문장으로 씁니다
- PARTIAL: 일부 요소만 확인되고 핵심(경험면접은 본인 행동이나 결과, 상황면접은 이유)이 빠졌다. 관련 경험이 없다고 한 경우도 포함
- VAGUE: 추상적이고 일반론이라 구체적 사례나 행동을 확인할 수 없다
여러 개에 해당하면 INCONSISTENT, OFF_TOPIC, VAGUE, PARTIAL 순으로 우선합니다.

[10. 출력 형식 (반드시 지킬 것)]
모든 칸을 채웁니다. 해당 없는 칸은 빈 문자열 "" 또는 빈 목록 [] 으로 둡니다.
action=ask_follow_up 이면 question_source 로 질문을 정확히 하나 지정합니다.
- original: follow_up_id 에 후보 ID 를 쓰고 generated_question 은 ""
- generated: generated_question 에 질문 문장을 쓰고 follow_up_id 는 ""
- fallback_text: 문항의 fallback_text 를 그대로 사용 (follow_up_id, generated_question 모두 "")
action 이 ask_follow_up 이 아니면 question_source=none. INCONSISTENT 가 아니면 inconsistency_note="".
action=ask_follow_up 인데 question_source=none 이거나 질문 칸이 비어 있으면 잘못된 출력입니다.
rationale 은 한국어 한두 문장으로 씁니다.
"""


class JudgeOutput(BaseModel):
    """LLM 이 채우는 출력. 그대로 쓰지 않고 안전장치를 거쳐 FollowUpDecision 으로 바뀝니다.

    모든 칸을 필수로 두었습니다. 선택 칸으로 두면 모델이 질문 칸을 빼먹는 일이 실제로 있었음 (첫 평가 4/14건).
    칸 순서도 의도적입니다: 요소 확인 → 판단 → 질문 선택 → 근거.
    """

    covered: list[AnswerElement]
    missing: list[AnswerElement]
    covered_intent_ids: list[str]
    action: Literal["ask_follow_up", "repeat_question", "close"]
    question_source: Literal["original", "generated", "fallback_text", "none"]
    follow_up_id: str = Field(description='원본 후보 ID. 없으면 ""')
    generated_question: str = Field(description='직접 만든 질문. 없으면 ""')
    verification_point_id: str = Field(description='확인하려는 검증 포인트 ID. 없으면 ""')
    quality: Literal["SUFFICIENT", "OFF_TOPIC", "INCONSISTENT", "PARTIAL", "VAGUE", "none"] = Field(
        description="action=close 일 때 답변 전체 품질. 아니면 none")
    inconsistency_note: str = Field(description='INCONSISTENT 일 때 무엇과 무엇이 어긋나는지. 아니면 ""')
    rationale: str


def _elements(q: Question) -> list[str]:
    if q.question_type is QuestionType.BEHAVIORAL:
        return ["situation", "task", "action", "result", "learning"]
    return ["judgment", "reason", "alternative", "expected_outcome"]


def build_prompt(
    question: Question,
    thread: QuestionThread,
    remaining_follow_ups: int,
    pressure_level: str,
    points: list[VerificationPoint],
    target_role: str | None,
    competency_description: str,
    candidate_context: str | None = None,
) -> str:
    used = thread.used_follow_up_ids
    fallback_used = bool(question.fallback_text) and any(t.text == question.fallback_text for t in thread.turns)
    candidates = []
    for f in question.follow_ups:
        if f.id in used:
            continue
        c = {"id": f.id, "text": f.text}
        if f.kind:
            c["kind"] = f.kind.value
        if f.note and f.kind and f.kind.value == "condition":
            c["condition"] = f.note
        if question.follow_ups_shared_with:
            c["shared"] = True
        candidates.append(c)

    asked_text = thread.turns[0].text
    info = {
        "문항ID": question.id,
        "유형": question.question_type_label,
        "역량": f"{question.competency_name}: {competency_description}",
        "실제로_한_질문": asked_text,
        "원본_질문": question.text if question.text != asked_text else None,
        "확인할_요소": _elements(question),
        "질문_의도": [{"id": i.id, "text": i.text} for i in question.intents],
        "Positive_체크포인트": [c.text for c in question.checkpoints.positive],
        "Negative_체크포인트": [c.text for c in question.checkpoints.negative],
        "fallback_text": question.fallback_text if question.fallback_text and not fallback_used else None,
    }
    info = {k: v for k, v in info.items() if v is not None}
    state = {
        "남은_꼬리질문": remaining_follow_ups,
        "압박_수준": pressure_level,
        "지원_직무": target_role,
    }
    lines = [
        "## 문항", json.dumps(info, ensure_ascii=False, indent=1),
        "## 원본 꼬리질문 후보 (아직 쓰지 않은 것)", json.dumps(candidates, ensure_ascii=False, indent=1),
        "## 진행 상태", json.dumps(state, ensure_ascii=False),
    ]
    if points:
        lines += ["## 검증 포인트", json.dumps(
            [{"id": p.id, "출처": "서류" if p.source == "documents" else "자기소개", "claim": p.claim, "concern": p.concern}
             for p in points], ensure_ascii=False, indent=1)]
    if candidate_context:
        lines += ["## 지원자 맥락 (모순 확인용)", candidate_context]
    lines += ["## 지금까지의 대화 (마지막이 직전 답변)", thread.transcript()]
    return "\n".join(lines)
