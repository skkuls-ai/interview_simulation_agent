from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile

from ..errors import ApiError
from ..graph import run_prepare
from ..schemas.api import CreateInterviewResponse, InterviewStatusResponse, PublicQuestion
from ..schemas.state import SessionStatus
from ..store import store

router = APIRouter(prefix="/api/interviews")

DOCS = ("resume", "job_posting", "job_description", "cover_letter")


async def _doc_text(name: str, text: str | None, file: UploadFile | None) -> str:
    if file is not None and file.filename:
        # PDF·DOCX 추출은 W-28(A) 담당. 지금은 텍스트 파일만 읽는다.
        raw = await file.read()
        if not file.filename.lower().endswith(".txt"):
            raise ApiError("TEXT_EXTRACTION_FAILED", "파일에서 텍스트를 읽지 못했습니다", field=name)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ApiError("TEXT_EXTRACTION_FAILED", "파일에서 텍스트를 읽지 못했습니다", field=name)
    if not text or not text.strip():
        raise ApiError("MISSING_REQUIRED_DOC", "필수 서류가 비어 있습니다", field=name)
    return text


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
    texts = {
        "resume": await _doc_text("resume", resume_text, resume_file),
        "job_posting": await _doc_text("job_posting", job_posting_text, job_posting_file),
        "job_description": await _doc_text("job_description", job_description_text, job_description_file),
        "cover_letter": await _doc_text("cover_letter", cover_letter_text, cover_letter_file),
    }
    if not privacy_consent:
        raise ApiError("CONSENT_REQUIRED", "개인정보 수집·이용에 동의해야 합니다")
    record = store.create(
        resume_text=texts["resume"],
        job_posting_text=texts["job_posting"],
        job_description_text=texts["job_description"],
        cover_letter_text=texts["cover_letter"],
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
