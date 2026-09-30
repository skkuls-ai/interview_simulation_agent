"""면접 그래프 상태 정의.

구성
- 설정: SessionConfig, PassRule
- 진행: QuestionThread, Turn, FollowUpDecision, VerificationPoint, IntroCheck
- 입력 지표: SpeechMetrics(STT), VisionMetrics(브라우저 MediaPipe)
- 평가 결과: ThreadEvaluation, IntroEvaluation, ObserverReport, CHRODecision, TimeReport, FinalFeedback
- 그래프 상태: InterviewState
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from .blueprint import CATEGORY_ORDER, InterviewBlueprint, VerificationPoint  # noqa: F401 (VerificationPoint 재공개)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- 설정


class Mode(str, Enum):
    PRACTICE = "practice"  # 문항 평가가 끝나는 대로 화면에 보여줌
    REAL = "real"  # 면접이 끝난 뒤 한꺼번에 보여줌


class PassRule(_Model):
    """CHRO 합불 규칙. 판정은 코드가 하고 LLM 은 근거 문장만 씁니다. 자기소개와 마무리는 반영하지 않습니다."""

    min_average: float = Field(3.0, ge=1, le=5)
    min_each_competency: float = Field(2.0, ge=1, le=5, description="과락 기준")
    hold_margin: float = Field(0.3, ge=0, description="평균이 기준 ± 이 범위면 보류")
    unasked_category_policy: Literal["hold", "fail"] = Field(
        "hold", description="시간 부족으로 묻지 못한 영역이 있을 때: 최대 보류(hold) 또는 불합격(fail)"
    )
    include_nonverbal: bool = False


class SessionConfig(_Model):
    mode: Mode = Mode.REAL
    category_order: list[str] = Field(default_factory=lambda: list(CATEGORY_ORDER))
    questions_per_category: int = Field(2, ge=1, le=5)
    max_extra_per_category: int = Field(1, ge=0, le=2, description="근거가 부족할 때 추가로 묻는 문항 수")
    required_evidence_threads: int | None = Field(
        None, description="영역별로 근거가 충분한 문항이 이 수보다 적으면 추가 문항. None 이면 questions_per_category"
    )
    max_follow_ups: int = Field(3, ge=0, le=6)
    pressure_level: Literal["low", "normal", "high"] = Field("normal", description="high 일 때만 압박 질문 사용")
    max_repeats_per_question: int = Field(2, ge=0, le=5, description="질문 다시 듣기 요청 허용 횟수 (문항당)")
    think_time_sec: int = Field(5, ge=0, description="모든 질문 공통 준비시간")
    answer_soft_limit_sec: int = Field(60, ge=10, description="권장 답변 시간. 넘으면 경고만 하고 끊지 않음")
    answer_budget_min: float = Field(45, gt=0, description="지원자 답변 시간의 합계 상한 (질문 읽기, 준비시간 제외)")
    use_camera: bool = True
    pass_rule: PassRule = Field(default_factory=PassRule)

    @property
    def evidence_threshold(self) -> int:
        return self.required_evidence_threads or self.questions_per_category


# ---------------------------------------------------------------- 입력 지표


class SpeechMetrics(_Model):
    duration_sec: float = Field(ge=0, description="실제 발화 시간")
    words_per_min: float | None = Field(None, ge=0)
    pause_ratio: float | None = Field(None, ge=0, le=1)
    long_pauses: int = Field(0, ge=0, description="3초 이상 침묵 횟수")
    filler_count: int = Field(0, ge=0, description="'음', '어' 같은 군말 횟수")
    response_latency_sec: float | None = Field(None, ge=0, description="답변 시간 시작 후 말을 시작하기까지")


class VisionMetrics(_Model):
    face_detected_ratio: float = Field(ge=0, le=1)
    gaze_on_screen_ratio: float | None = Field(None, ge=0, le=1)
    head_turn_events: int = Field(0, ge=0)
    blink_per_min: float | None = Field(None, ge=0)
    smile_ratio: float | None = Field(None, ge=0, le=1)


class CandidateAnswer(_Model):
    """답변 대기에서 재개할 때 넘기는 값."""

    text: str = Field(description="STT 최종 결과. 비어 있으면 무응답으로 처리")
    answer_duration_sec: float = Field(
        ge=0, description="준비시간이 끝난 시점부터 답변 완료 버튼까지. 시간 예산과 초과 시간 계산 기준"
    )
    speech: SpeechMetrics | None = None
    vision: VisionMetrics | None = None
    sequence: int | None = Field(
        None, description="답하는 질문 화면의 sequence. 재전송된 요청이 다른 질문의 답으로 기록되는 것을 막음"
    )


# ---------------------------------------------------------------- 진행

Stage = Literal["intro", "main", "closing"]


class Turn(_Model):
    speaker: Literal["interviewer", "candidate"]
    kind: Literal["main", "follow_up", "generated_follow_up", "repeat", "answer", "no_response"]
    text: str
    lead_in: str | None = Field(None, description="전환 멘트. 화면에는 질문만, TTS 는 멘트와 질문을 이어서 읽음")
    follow_up_id: str | None = None
    verification_point_id: str | None = None
    at: datetime | None = None
    answer_duration_sec: float | None = None
    overtime_sec: float | None = None
    speech: SpeechMetrics | None = None
    vision: VisionMetrics | None = None


class AnswerElement(str, Enum):
    SITUATION = "situation"
    TASK = "task"
    ACTION = "action"
    RESULT = "result"
    LEARNING = "learning"
    JUDGMENT = "judgment"
    REASON = "reason"
    ALTERNATIVE = "alternative"
    EXPECTED_OUTCOME = "expected_outcome"


class AnswerQuality(str, Enum):
    """문항이 닫힐 때 답변 전체를 종합한 품질. 꼬리질문 판단 에이전트가 붙입니다."""

    SUFFICIENT = "SUFFICIENT"      # 질문 의도를 판단할 근거가 충분
    OFF_TOPIC = "OFF_TOPIC"        # 질문과 무관한 답변
    INCONSISTENT = "INCONSISTENT"  # 서류, 자기소개, 앞선 답변과 모순
    PARTIAL = "PARTIAL"            # 일부 요소만 있고 핵심이 빠짐
    VAGUE = "VAGUE"                # 추상적이고 구체적 사례나 행동이 없음


class FollowUpDecision(_Model):
    action: Literal["ask_follow_up", "repeat_question", "close"]
    covered: list[AnswerElement] = Field(default_factory=list)
    missing: list[AnswerElement] = Field(default_factory=list)
    covered_intent_ids: list[str] = Field(default_factory=list)
    follow_up_id: str | None = None
    generated_question: str | None = None
    verification_point_id: str | None = Field(None, description="자기소개 검증 포인트를 확인하려는 꼬리질문일 때")
    quality: AnswerQuality | None = Field(None, description="action=close 일 때 답변 전체 품질")
    inconsistency_note: str | None = Field(None, description="INCONSISTENT 일 때 무엇과 무엇이 모순인지")
    decided_by: Literal["llm", "rule", "fallback"] = Field(
        "rule", description="llm: 모델 판단, rule: 그래프 규칙(예산, 한도), fallback: 모델 실패로 기본 규칙 적용"
    )
    evidence_sufficient: bool = Field(
        True, description="close 일 때: 평가할 근거가 충분한지. 관련 경험이 없다고 답해 더 묻는 의미가 없으면 False"
    )
    rationale: str


class IntroCheck(_Model):
    """자기소개 직후 그래프 안에서 빠르게 뽑는 정보. 이후 질문 개인화와 검증에 사용."""

    stated_motivation: str | None = None
    stated_aspiration: str | None = None
    mentioned_experience_ids: list[str] = Field(default_factory=list)
    verification_points: list[VerificationPoint] = Field(default_factory=list)


CloseReason = Literal["sufficient", "insufficient", "max_follow_ups", "budget_exhausted", "skipped", "single_turn"]


class QuestionThread(_Model):
    thread_id: str = Field(description="intro, closing, 또는 문항 ID")
    stage: Stage
    question_id: str | None = None
    category_code: str | None = None
    competency_code: str | None = None
    is_extra: bool = Field(False, description="근거 부족으로 추가한 문항")
    turns: list[Turn] = Field(default_factory=list)
    decisions: list[FollowUpDecision] = Field(default_factory=list)
    closed: bool = False
    close_reason: CloseReason | None = None
    quality: AnswerQuality | None = None
    inconsistency_note: str | None = None

    @property
    def evidence_ok(self) -> bool:
        if self.quality is not None:
            return self.quality is AnswerQuality.SUFFICIENT
        return self.close_reason == "sufficient"

    @property
    def follow_up_count(self) -> int:
        return sum(1 for t in self.turns if t.speaker == "interviewer" and t.kind in ("follow_up", "generated_follow_up"))

    @property
    def used_follow_up_ids(self) -> set[str]:
        return {t.follow_up_id for t in self.turns if t.follow_up_id}

    @property
    def last_interviewer_turn(self) -> Turn | None:
        return next((t for t in reversed(self.turns) if t.speaker == "interviewer"), None)

    @property
    def answer_seconds(self) -> float:
        return sum(t.answer_duration_sec or 0 for t in self.turns if t.speaker == "candidate")

    def transcript(self) -> str:
        label = {"interviewer": "면접관", "candidate": "지원자"}
        return "\n".join(
            f"{label[t.speaker]}: {t.text}" for t in self.turns if t.kind != "no_response"
        )


# ---------------------------------------------------------------- 평가 결과


class CheckpointHit(_Model):
    checkpoint_id: str
    evidence: str = Field(description="지원자 발언 인용")


class VerificationResult(_Model):
    point_id: str
    result: Literal["supported", "contradicted", "insufficient"]
    evidence: str


class PanelMember(_Model):
    """평가자 1명의 채점과 검증 결과."""

    index: int
    score: int | None = Field(None, ge=1, le=5)
    valid: bool
    re_evaluated: bool = False
    issues: list[str] = Field(default_factory=list, description="코드 검증, 검증 에이전트가 찾은 문제")


class ThreadEvaluation(_Model):
    """문항 1개 평가. 평가자 3명의 결과를 합친 것이며 그래프 밖 백그라운드에서 만들어집니다."""

    thread_id: str
    question_id: str
    competency_code: str
    score: int | None = Field(ge=1, le=5, description="유효 평가자 점수의 중앙값. 판단 보류면 None")
    status: Literal["ok", "disputed", "undetermined"] = Field(
        "ok", description="disputed: 평가자 간 2점 이상 차이, undetermined: 유효 평가자 1명 이하 (판단 보류)"
    )
    panel: list[PanelMember] = Field(default_factory=list)
    positive_hits: list[CheckpointHit] = Field(default_factory=list)
    negative_hits: list[CheckpointHit] = Field(default_factory=list)
    covered_intent_ids: list[str] = Field(default_factory=list)
    verification_results: list[VerificationResult] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class DimensionScore(_Model):
    score: int = Field(ge=1, le=5)
    comment: str


class IntroGuide(_Model):
    """자기소개를 더 구체적이고 이력에 맞게 고치기 위한 가이드."""

    motivation_points: list[str] = Field(description="이 회사여야 하는 이유로 쓸 수 있는 이력과 JD 연결점")
    aspiration_points: list[str] = Field(description="이력에 근거한 입사 후 포부")
    suggested_outline: list[str] = Field(description="1분 자기소개 구성 제안")


class IntroEvaluation(_Model):
    """자기소개 평가 (JD 를 쓴 회사 담당자 관점). 합불에는 반영하지 않고 피드백에만 사용."""

    why_this_company: DimensionScore = Field(description="이 회사여야만 하는 이유가 명확한가")
    aspiration: DimensionScore = Field(description="포부가 직무와 회사에 맞고 구체적인가")
    experience_fit: DimensionScore = Field(description="제시한 경험이 JD 직무에 맞는가")
    summary: str
    guide: IntroGuide


class ObserverNote(_Model):
    thread_id: str
    observation: str
    tip: str | None = None


class ObserverReport(_Model):
    notes: list[ObserverNote] = Field(default_factory=list)
    summary: str
    coaching_points: list[str] = Field(default_factory=list)
    nonverbal_score: float | None = Field(None, ge=1, le=5)


class RuleCheck(_Model):
    name: str
    passed: bool
    detail: str


class CHRODecision(_Model):
    decision: Literal["pass", "hold", "fail"]
    average_score: float
    competency_scores: dict[str, float]
    category_scores: dict[str, float]
    unasked_categories: list[str] = Field(default_factory=list)
    inconsistent_threads: list[str] = Field(default_factory=list)
    undetermined_threads: list[str] = Field(default_factory=list)
    disputed_threads: list[str] = Field(default_factory=list)
    rule_checks: list[RuleCheck]
    rationale: str


class OvertimeAnswer(_Model):
    thread_id: str
    stage: Stage
    question_text: str
    duration_sec: float
    overtime_sec: float


class TimeReport(_Model):
    """시간 사용 리포트. 코드가 계산하므로 LLM 이 빠뜨릴 수 없습니다."""

    budget_sec: float
    total_answer_sec: float
    budget_exhausted: bool
    overtime_answers: list[OvertimeAnswer]
    unasked_categories: list[str]
    cut_categories: dict[str, int] = Field(default_factory=dict)
    messages: list[str] = Field(description="피드백에 그대로 넣는 문장")


class FollowUpRisk(_Model):
    """다음 면접에서 추가 질문을 받을 수 있는 답변 (INCONSISTENT)."""

    thread_id: str
    question_text: str
    note: str = Field(description="무엇과 무엇이 어긋났는지")
    tip: str


class CompetencyAdvice(_Model):
    competency_code: str
    advice: str
    better_answer_hint: str | None = None


class Quote(_Model):
    quote_id: str = Field(pattern=r"^QT-\d{3}$")
    question_id: str
    text: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class FinalFeedback(_Model):
    headline: str
    strengths: list[str]
    improvements: list[CompetencyAdvice]
    quotes: list[Quote] = Field(default_factory=list)
    intro_feedback: IntroEvaluation | None = None
    time_management: TimeReport
    follow_up_risks: list[FollowUpRisk] = Field(default_factory=list)
    answer_quality: dict[str, int] = Field(default_factory=dict, description="답변 품질 분류별 문항 수")
    nonverbal_tips: list[str] = Field(default_factory=list)
    next_practice_question_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- 그래프 상태


def upsert(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}


Phase = Literal["ready", "intro", "interviewing", "closing", "evaluating", "done"]


class InterviewState(TypedDict, total=False):
    session_id: str
    config: SessionConfig
    blueprint: InterviewBlueprint

    phase: Phase
    interview_started_at: datetime  # 준비시간이 끝난 시점
    category_index: int
    asked: dict[str, list[str]]  # 영역별로 이미 물은 문항 ID
    active_thread_id: str
    threads: Annotated[dict[str, QuestionThread], upsert]
    intro_check: IntroCheck
    verification_points: Annotated[dict[str, VerificationPoint], upsert]
    answer_seconds_used: float
    unasked_categories: list[str]  # 시간 부족으로 한 문항도 못 물은 영역
    cut_categories: dict[str, int]  # 시간 부족으로 못 물은 기본 문항 수 (영역별, 일부만 못 물은 경우 포함)

    evaluations: dict[str, ThreadEvaluation]  # 그래프 밖에서 만들어져 마지막에 전달됨
    intro_evaluation: IntroEvaluation
    observer_report: ObserverReport
    chro_decision: CHRODecision
    time_report: TimeReport
    final_feedback: FinalFeedback
