"""FastAPI 앱. SessionService 를 얇게 감쌉니다.

    python -m backend.api          (.env 의 APP_HOST, APP_PORT, DEBUG 사용)

음성 스트리밍(WebSocket)은 STT/TTS 를 붙이는 단계에서 추가합니다.
지금은 STT 결과 텍스트와 답변 시간을 REST 로 받습니다.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..interview.agents import StubAnalysisAgents, StubEvaluationAgents, StubInterviewAgents
from ..interview.serde import make_sqlite_checkpointer
from ..interview.state import SessionConfig
from ..question_bank.models import QuestionBank
from ..service.consent import CONSENT_TERMS, ConsentRecord
from ..service.documents import DocumentError, DocumentStore
from ..service.session_service import SessionError, SessionService, TemporaryFailure
from ..service.store import Store

from ..config import ROOT, settings

DATA_DIR = settings.data_dir
PURGE_INTERVAL_SEC = 600


def _interview_agents(bank: QuestionBank):
    """INTERVIEW_USE_LLM=1 이면 꼬리질문 판단에 Gemini 사용."""
    if settings.use_llm:
        from ..interview.llm_agents import HybridInterviewAgents
        from ..llm.client import GeminiClient

        return HybridInterviewAgents(bank, GeminiClient())
    return StubInterviewAgents(bank)


def _evaluation_agents(bank: QuestionBank):
    """INTERVIEW_USE_LLM=1 이면 평가자 3명 패널 + 검증 에이전트 (Gemini)."""
    if settings.use_llm:
        from ..interview.evaluation import gemini_evaluation_agents
        from ..llm.client import GeminiClient

        return gemini_evaluation_agents(bank, GeminiClient(), concurrency=settings.bg_llm_concurrency)
    return StubEvaluationAgents()


def build_service(data_dir: Path = DATA_DIR) -> SessionService:
    data_dir.mkdir(parents=True, exist_ok=True)
    bank = QuestionBank.load(str(ROOT / "backend/question_bank/question_bank.json"))
    return SessionService(
        bank=bank,
        analysis_agents=StubAnalysisAgents(),  # TODO: LLM 버전으로 교체
        interview_agents=_interview_agents(bank),
        evaluation_agents=_evaluation_agents(bank),
        store=Store(data_dir / "app.db"),
        documents=DocumentStore(data_dir / "uploads"),
        checkpointer=make_sqlite_checkpointer(str(data_dir / "checkpoints.db")),
    )


class CreateSession(BaseModel):
    consent: ConsentRecord
    config: SessionConfig | None = None


class AnalyzeRequest(BaseModel):
    target_role: str | None = None


def create_app(service: SessionService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.service = service or build_service()

        async def purge_loop():
            # 동의서 약속: 끝나지 않은 세션의 문서와 기록은 24시간 뒤 삭제
            while True:
                await asyncio.to_thread(app.state.service.purge_expired)
                await asyncio.sleep(PURGE_INTERVAL_SEC)

        task = asyncio.create_task(purge_loop())
        yield
        task.cancel()
        app.state.service.shutdown()

    app = FastAPI(title=settings.app_name, version=settings.app_version, debug=settings.debug, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.frontend_origin.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"app": settings.app_name, "version": settings.app_version, "llm": settings.use_llm}

    def svc() -> SessionService:
        return app.state.service

    def guard(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (SessionError, DocumentError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        except TemporaryFailure as e:
            raise HTTPException(status_code=503, detail=str(e))
        except ValueError as e:  # 요청 형식 오류 (pydantic)
            raise HTTPException(status_code=422, detail=str(e))

    @app.get("/consent")
    def consent_terms():
        return CONSENT_TERMS

    @app.post("/sessions")
    def create_session(body: CreateSession):
        return {"session_id": guard(svc().create_session, body.consent, body.config)}

    @app.get("/sessions")
    def in_progress():
        return svc().in_progress_sessions()

    @app.post("/sessions/{sid}/documents")
    async def upload(sid: str, kind: Literal["jd", "resume", "cover_letter"] = Form(...), file: UploadFile = File(...)):
        data = await file.read()
        return guard(svc().upload_document, sid, kind, file.filename or "upload.txt", data)

    @app.post("/sessions/{sid}/analyze")
    def analyze(sid: str, body: AnalyzeRequest):
        bp = guard(svc().analyze, sid, body.target_role)
        # 면접 구성 안내만 공개 (질문 내용은 비공개)
        return {"personalized": bp.personalized, "guide": bp.guide.model_dump(mode="json")}

    @app.post("/sessions/{sid}/start")
    def start(sid: str):
        return guard(svc().start, sid).model_dump(mode="json")

    @app.post("/sessions/{sid}/actions")
    def act(sid: str, payload: dict[str, Any]):
        return guard(svc().act, sid, payload).model_dump(mode="json")

    @app.post("/sessions/{sid}/finish")
    def finish(sid: str):
        return guard(svc().finish, sid).model_dump(mode="json")

    @app.get("/sessions/{sid}/resume")
    def resume(sid: str):
        return guard(svc().resume_view, sid).model_dump(mode="json")

    @app.post("/sessions/{sid}/abandon")
    def abandon(sid: str):
        guard(svc().abandon, sid)
        return {"ok": True}

    @app.get("/results")
    def results():
        return svc().list_results()

    @app.get("/results/{sid}")
    def result(sid: str):
        return guard(svc().get_result, sid)

    @app.delete("/results/{sid}")
    def delete_result(sid: str):
        guard(svc().delete_result, sid)
        return {"ok": True}

    return app


app = create_app()
