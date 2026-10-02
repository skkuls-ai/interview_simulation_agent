import json
import os
import tempfile

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile

from ..audio import transcribe_and_delete
from ..errors import ApiError
from ..graph import run_evaluate
from ..graph.evaluate import STEPS as EVALUATE_STEPS
from ..schemas.api import DeliveryMetricsInput, SubmitAnswerResponse
from ..schemas.state import Answer, DeliveryMetrics, SessionStatus, Step, StepState, TranscriptStatus
from ..store import store

router = APIRouter(prefix="/api/interviews")


@router.post("/{session_id}/answers", status_code=202, response_model=SubmitAnswerResponse)
async def submit_answer(
    session_id: str,
    background: BackgroundTasks,
    question_id: str = Form(...),
    duration_sec: float = Form(...),
    timed_out: bool = Form(False),
    delivery_metrics: str | None = Form(None),
    audio: UploadFile | None = File(None),
):
    record = store.get(session_id)
    if record is None:
        raise ApiError("SESSION_NOT_FOUND", "세션을 찾을 수 없습니다")
    state = record.state

    # 같은 question_id가 다시 오면 이전 응답을 그대로 돌려준다 (재전송 안전)
    if question_id in record.answer_responses:
        return record.answer_responses[question_id]
    if state.status not in (SessionStatus.READY, SessionStatus.IN_PROGRESS):
        raise ApiError("NOT_IN_PROGRESS", "진행 가능한 상태가 아닙니다")
    order = [q.question_id for q in sorted(state.questions, key=lambda q: q.order)]
    if question_id not in order:
        raise ApiError("UNKNOWN_QUESTION", "없는 질문입니다")

    delivery = None
    if delivery_metrics:
        try:
            delivery = DeliveryMetrics(**DeliveryMetricsInput.model_validate(json.loads(delivery_metrics)).model_dump())
        except ValueError:
            delivery = None  # 측정값은 점수에 반영하지 않으므로 형식이 틀려도 답변은 받는다

    audio_path = None
    if audio is not None and audio.filename:
        fd, audio_path = tempfile.mkstemp(suffix=".webm")
        with os.fdopen(fd, "wb") as f:
            f.write(await audio.read())

    following = order[order.index(question_id) + 1:]
    next_id = following[0] if following else None
    status = SessionStatus.IN_PROGRESS if next_id else SessionStatus.EVALUATING

    with store.lock:
        state.answers.append(Answer(
            question_id=question_id, duration_sec=duration_sec, timed_out=timed_out, delivery=delivery,
            transcript_status=TranscriptStatus.PENDING,
        ))
        state.status = status
        if status == SessionStatus.EVALUATING:
            # 답변 변환이 끝나 평가가 시작되기 전에도 화면 6이 평가 단계를 보이게 한다
            state.steps = [Step(step_id=i, label=label, state=StepState.RUNNING if i == "transcribe" else StepState.PENDING)
                           for i, label in EVALUATE_STEPS]
        response = SubmitAnswerResponse(question_id=question_id, received=True,
                                        next_question_id=next_id, status=status)
        record.answer_responses[question_id] = response

    background.add_task(transcribe_and_delete, store, session_id, question_id, audio_path)
    if status == SessionStatus.EVALUATING:
        background.add_task(run_evaluate, store, session_id)
    return response
