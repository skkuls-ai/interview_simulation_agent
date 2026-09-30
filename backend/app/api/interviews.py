from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile

from ..errors import ApiError
from ..graph import run_prepare
from ..nodes.prep.documents import DocumentError, collect_documents
from ..schemas.api import CreateInterviewResponse, InterviewStatusResponse, PublicQuestion
from ..schemas.state import SessionStatus
from ..store import store

router = APIRouter(prefix="/api/interviews")

DOCS = ("resume", "job_posting", "job_description", "cover_letter")


async def _read_file(file: UploadFile | None) -> tuple[str, bytes] | None:
    if file is None or not file.filename:
        return None
    return file.filename, await file.read()


@router.post("", status_code=201, response_model=CreateInterviewResponse)
async def create_interview(
    background: BackgroundTasks,
    resume_text: str | None = Form(None),
    resume_file: UploadFile | None = File(None),
    job_posting_text: str | None = Form(None),
    job_posting_file: UploadFile | None = File(None),
    job_description_text: str | None = Form(None),
    job_description_file: UploadFile | None = File(None),
    cover_letter_text: str | None = Form(None),
    cover_letter_file: UploadFile | None = File(None),
    privacy_consent: bool = Form(False),
):
    # 서류 4종 텍스트 추출 (W-28, A). 검사 순서: 동의 → 필수 서류 → 텍스트 추출 (08 T-109, T-209, T-107)
    files = {
        "resume": await _read_file(resume_file),
        "job_posting": await _read_file(job_posting_file),
        "job_description": await _read_file(job_description_file),
        "cover_letter": await _read_file(cover_letter_file),
    }
    texts = {"resume": resume_text, "job_posting": job_posting_text,
             "job_description": job_description_text, "cover_letter": cover_letter_text}
    try:
        docs = collect_documents(files=files, texts=texts, privacy_consent=privacy_consent)
    except DocumentError as e:
        raise ApiError(e.code, e.message, field=e.field) from None
    record = store.create(
        resume_text=docs.resume_text,
        job_posting_text=docs.job_posting_text,
        job_description_text=docs.job_description_text,
        cover_letter_text=docs.cover_letter_text,
    )
    background.add_task(run_prepare, store, record.state.session_id)
    return CreateInterviewResponse(session_id=record.state.session_id, status=SessionStatus.PREPARING)


@router.get("/{session_id}", response_model=InterviewStatusResponse)
def get_interview(session_id: str):
    record = store.get(session_id)
    if record is None:
        raise ApiError("SESSION_NOT_FOUND", "세션을 찾을 수 없습니다")
    with store.lock:
        state = record.state
        questions = None
        if state.questions and state.status != SessionStatus.PREPARING:
            # 면접 중에는 기대 요소·평가 기준·연결 정보를 내보내지 않는다
            questions = [PublicQuestion(question_id=q.question_id, order=q.order, type=q.type, text=q.text)
                         for q in state.questions]
        return InterviewStatusResponse(
            session_id=state.session_id, status=state.status, steps=list(state.steps),
            questions=questions, error=state.error,
        )
