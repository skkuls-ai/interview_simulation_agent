"""준비 그래프: 서류 분석(A) → 질문 준비 → READY.

질문 생성(B)은 아직 없어서 questions·review 단계는 shared/mock의 질문 5개로 채운다(임시).
B 노드가 합류하면 _temp_questions() 호출만 바꾼다."""
import logging

from ..nodes.prep.analysis import run_analysis
from ..schemas.state import Question, SessionStatus, Step, StepState
from ..store import Store
from .llm_factory import get_llm
from .mock_data import load

log = logging.getLogger(__name__)

STEPS = [
    ("read_posting", "채용공고 읽는 중"),
    ("read_resume", "이력서·자소서 읽는 중"),
    ("link", "공고와 경험 연결 중"),
    ("checkpoints", "검증 포인트 찾는 중"),
    ("questions", "질문 준비 중"),
    ("review", "질문 검수 중"),
]


def _temp_questions() -> list[Question]:
    return [Question(**q) for q in load("session_ready.json")["questions"]]


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
        _set_step(record, store, "questions", "RUNNING")
        questions = _temp_questions()
        _set_step(record, store, "questions", "DONE", "임시 질문 5개")
        _set_step(record, store, "review", "DONE")
        with store.lock:
            record.state.questions = questions
            record.state.status = SessionStatus.READY
    except Exception as e:
        log.exception("준비 그래프 실패")
        with store.lock:
            record.state.status = SessionStatus.FAILED
            record.state.error = f"서류 분석 중 오류가 발생했습니다 ({type(e).__name__})"
