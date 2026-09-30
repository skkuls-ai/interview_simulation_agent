"""평가 그래프: STT 대기 → 피드백 생성(E) → COMPLETED.

E의 evaluate_state가 태도·직무 적합성·일관성·질문별을 한 번에 돌리므로(05 문서 10절 예외),
순서는 이 파일에서 '대기 → 평가 → 저장'만 정한다."""
import logging
import time

from pydantic import ValidationError

from ..nodes.evaluate.runner import evaluate_state
from ..schemas.api import ReportResponse
from ..schemas.state import Report, SessionStatus, Step, StepState, TranscriptStatus
from ..store import Store
from .llm_factory import get_llm

log = logging.getLogger(__name__)

STEPS = [
    ("transcribe", "답변 변환 중"),
    ("attitude", "태도 분석 중"),
    ("job_fit", "직무 적합성 분석 중"),
    ("consistency", "답변 일관성 분석 중"),
    ("compose", "피드백 정리 중"),
]


def _set_step(record, store: Store, step_id: str, state: str, detail: str | None = None) -> None:
    with store.lock:
        for step in record.state.steps:
            if step.step_id == step_id:
                step.state = StepState(state)
                if detail is not None:
                    step.detail = detail
                return


def _wait_for_transcripts(record, store: Store, timeout: float, poll: float) -> None:
    """답변이 모두 PENDING이 아니게 되면 끝낸다. 시간을 넘기면 남은 PENDING을 FAILED로 둔다."""
    deadline = time.monotonic() + timeout
    while True:
        with store.lock:
            answers = record.state.answers
            expected = len(record.state.questions)
            pending = [a for a in answers if a.transcript_status == TranscriptStatus.PENDING]
            if len(answers) >= expected and not pending:
                return
            if time.monotonic() >= deadline:
                for a in pending:
                    a.transcript_status = TranscriptStatus.FAILED
                    a.transcript = None
                return
        time.sleep(poll)


def run_evaluate(store: Store, session_id: str, llm=None, *,
                 stt_wait_sec: float = 30.0, poll_sec: float = 0.2) -> None:
    record = store.get(session_id)
    if record is None:
        return
    with store.lock:
        if record.evaluation_started or record.report_response is not None:
            return  # 중복 호출 방어
        record.evaluation_started = True
        record.state.steps = [Step(step_id=i, label=label, state=StepState.PENDING) for i, label in STEPS]
    try:
        _set_step(record, store, "transcribe", "RUNNING")
        _wait_for_transcripts(record, store, stt_wait_sec, poll_sec)
        with store.lock:
            total = len(record.state.answers)
            done = sum(a.transcript_status == TranscriptStatus.DONE for a in record.state.answers)
            snapshot = record.state.model_copy(deep=True)  # 평가 중 늦게 끝난 STT가 입력을 바꾸지 못하게
        _set_step(record, store, "transcribe", "DONE", f"답변 {total}개 중 {done}개 변환" if done < total else f"답변 {total}개 변환 완료")

        report = evaluate_state(snapshot, llm or get_llm(),
                                on_step=lambda step_id, state: _set_step(record, store, step_id, state))
        report["session_id"] = session_id
        response = ReportResponse.model_validate(report)

        with store.lock:
            record.report_response = response
            record.state.report = Report.model_validate(
                {k: report[k] for k in ("attitude", "job_fit", "consistency", "per_question")})
            for step in record.state.steps:
                step.state = StepState.DONE
            record.state.status = SessionStatus.COMPLETED
    except (Exception, ValidationError) as e:
        log.exception("평가 그래프 실패")
        with store.lock:
            record.state.status = SessionStatus.FAILED
            record.state.error = f"피드백 생성 중 오류가 발생했습니다 ({type(e).__name__})"
