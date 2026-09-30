"""화면과 백엔드가 주고받는 메시지 형식.

- Prompt: 그래프가 멈추면서(interrupt) 화면에 보내는 것. 화면 상태를 결정합니다.
- Resume: 사용자의 행동을 그래프에 돌려주는 것 (Command(resume=...)).
- ServiceEvent: 그래프 밖 세션 서비스가 보내는 알림 (면접관 대기, 문항 평가 도착, 재개 안내 등).
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from .blueprint import InterviewGuide
from .state import CandidateAnswer, IntroEvaluation, Stage, ThreadEvaluation


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- Prompt (그래프 → 화면)


class ReadyPrompt(_Model):
    """면접 구성 안내와 준비시간. 사용자가 '면접 시작'을 누르면 끝납니다."""

    type: Literal["await_ready"] = "await_ready"
    guide: InterviewGuide
    resumed: bool = False


class QuestionPrompt(_Model):
    """질문 표시와 음성 재생 → 준비시간 → 답변시간.

    화면 동작
    1. text 를 표시하고 lead_in + text 를 TTS 로 재생
    2. 재생이 끝나면 think_time_sec 카운트다운 표시
    3. 카운트다운이 끝나면 답변시간 시작 (이 시점부터 answer_duration_sec 측정)
    4. soft_limit_sec 를 넘으면 경고와 초과 시간(+mm:ss)을 표시하되 답변은 끊지 않음
    5. 답변 완료 버튼을 누르면 CandidateAnswer 전송
    """

    type: Literal["await_answer"] = "await_answer"
    thread_id: str
    stage: Stage
    kind: Literal["main", "follow_up", "generated_follow_up", "repeat"]
    lead_in: str | None
    text: str
    sequence: int = Field(description="몇 번째 질문 화면인지 (꼬리질문 포함). 영역은 공개하지 않음")
    think_time_sec: int
    soft_limit_sec: int
    resumed: bool = False


class NoResponsePrompt(_Model):
    type: Literal["no_response"] = "no_response"
    thread_id: str
    message: str = "다시 답변하시겠어요?"
    options: list[Literal["retry", "skip"]] = Field(default_factory=lambda: ["retry", "skip"])


class EvaluationsPending(_Model):
    """면접이 끝나 그래프 밖 평가를 기다리는 상태. 화면은 '결과 정리 중'을 표시."""

    type: Literal["await_evaluations"] = "await_evaluations"
    thread_ids: list[str]
    needs_intro_evaluation: bool


Prompt = Annotated[
    Union[ReadyPrompt, QuestionPrompt, NoResponsePrompt, EvaluationsPending], Field(discriminator="type")
]
PromptAdapter: TypeAdapter = TypeAdapter(Prompt)


# ---------------------------------------------------------------- Resume (화면 → 그래프)


class StartSignal(_Model):
    action: Literal["start"] = "start"


class NoResponseChoice(_Model):
    choice: Literal["retry", "skip"]


class EvaluationBundle(_Model):
    evaluations: dict[str, ThreadEvaluation]
    intro_evaluation: IntroEvaluation | None = None


__all__ = [
    "CandidateAnswer", "EvaluationBundle", "EvaluationsPending", "NoResponseChoice", "NoResponsePrompt",
    "Prompt", "PromptAdapter", "QuestionPrompt", "ReadyPrompt", "StartSignal",
]


# ---------------------------------------------------------------- ServiceEvent (서비스 → 화면)


class InterviewerThinking(_Model):
    """답변 완료 후 다음 질문이 나오기 전까지 표시. 꼬리질문 판단과 STT 처리 시간 동안."""

    type: Literal["interviewer_thinking"] = "interviewer_thinking"
    message: str = "면접관이 답변 내용을 정리하고 있습니다"


class QuestionFeedbackReady(_Model):
    """연습 모드에서 백그라운드 평가가 끝나면 보냄."""

    type: Literal["question_feedback"] = "question_feedback"
    thread_id: str
    evaluation: ThreadEvaluation


class ResumeStep(_Model):
    title: str
    detail: str


class ResumeView(_Model):
    """중단된 세션을 다시 열 때 보여주는 화면 정보."""

    type: Literal["resume_view"] = "resume_view"
    session_id: str
    phase: str
    answered_questions: int
    answer_minutes_used: float
    answer_minutes_left: float
    discarded_partial_answer: bool = Field(
        description="중단될 때 답변 중이었다면 그 답변은 저장되지 않았고 같은 질문을 다시 받음"
    )
    steps: list[ResumeStep]
    next_prompt: Prompt | None
