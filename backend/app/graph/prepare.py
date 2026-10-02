"""준비 그래프: 서류 분석과 질문 생성 → READY."""
import logging

from ..nodes.prep.analysis import run_analysis
from ..schemas.state import Question, QuestionType, SessionStatus, Step, StepState
from ..store import Store
from .llm_factory import get_llm

log = logging.getLogger(__name__)

STEPS = [
    ("read_posting", "채용공고 읽는 중"),
    ("read_resume", "이력서·자소서 읽는 중"),
    ("link", "공고와 경험 연결 중"),
    ("checkpoints", "검증 포인트 찾는 중"),
    ("competency_questions", "직무 적합 인성 질문 고르는 중"),
    ("technical_questions", "기술 면접 질문 만드는 중"),
]


def _intro_question() -> Question:
    return Question(
        question_id="Q-1",
        order=1,
        type=QuestionType.INTRO,
        text="1분 정도로 자기소개를 해 주세요. 지원 직무와 관련된 경험을 중심으로 말씀해 주세요.",
    )


def _set_step(record, store: Store, step_id: str, state: str, detail: str | None = None) -> None:
    with store.lock:
        for step in record.state.steps:
            if step.step_id == step_id:
                step.state = StepState(state)
                if detail is not None:
                    step.detail = detail
                return


def run_prepare(store: Store, session_id: str, llm=None) -> None:
    record = store.get(session_id)
    if record is None:
        return
    try:
        with store.lock:
            s = record.state
            texts = (s.resume_text, s.job_posting_text, s.job_description_text, s.cover_letter_text)
            s.steps = [Step(step_id=i, label=label, state=StepState.PENDING) for i, label in STEPS]

        llm = llm or get_llm()
        report = run_analysis(
            llm, *texts,
            on_step=lambda step_id, state, detail=None: _set_step(record, store, step_id, state, detail),
        )
        if report.fallbacks:
            log.warning("서류 분석에서 대체값을 쓴 단계: %s", report.fallbacks)

        with store.lock:
            record.state.analysis = report.analysis
            record.state.questions = sorted(
                [_intro_question(), *report.competency_questions, *report.technical_questions],
                key=lambda question: question.order,
            )
        with store.lock:
            record.state.status = SessionStatus.READY
    except Exception as e:
        log.exception("준비 그래프 실패")
        with store.lock:
            record.state.status = SessionStatus.FAILED
            record.state.error = f"서류 분석 중 오류가 발생했습니다 ({type(e).__name__})"
