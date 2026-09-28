from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from backend.interview.agents import StubAnalysisAgents, StubEvaluationAgents, StubInterviewAgents
from backend.interview.serde import make_sqlite_checkpointer
from backend.interview.state import SessionConfig
from backend.question_bank.models import QuestionBank
from backend.service.consent import ConsentRecord
from backend.service.documents import DocumentStore
from backend.service.session_service import ActResult, SessionService
from backend.service.store import Store

ROOT = Path(__file__).parents[1]
BANK = QuestionBank.load(str(ROOT / "backend/question_bank/question_bank.json"))

JD = """회사: 에이비씨테크
- 연간 300명 규모 채용 프로세스 기획과 운영
- 현업 리더와의 협업 및 커뮤니케이션
- 채용 데이터 분석과 개선 과제 도출
- 조직 변화 관리와 리더 지원
"""
RESUME = """- 스타트업에서 채용 프로세스 개편, 지원자 이탈률 개선
- 채용 데이터 대시보드 구축과 월간 리포트 작성
- 현업 면접관 교육 운영
"""

LONG = "당시 채용 프로세스를 맡아 지원자 이탈 원인을 분석했고, 안내 방식을 바꿔 이탈률을 낮췄습니다. " * 2
SHORT = "네, 그런 경험이 있습니다."


def full_consent(**kw) -> ConsentRecord:
    base = dict(microphone=True, camera=True, documents=True, store_results=True)
    base.update(kw)
    return ConsentRecord(**base)


def make_service(tmp: Path, *, eval_agents=None, interview_agents=None, events: list | None = None) -> SessionService:
    tmp.mkdir(parents=True, exist_ok=True)
    return SessionService(
        bank=BANK,
        analysis_agents=StubAnalysisAgents(),
        interview_agents=interview_agents or StubInterviewAgents(BANK),
        evaluation_agents=eval_agents or StubEvaluationAgents(),
        store=Store(tmp / "app.db"),
        documents=DocumentStore(tmp / "uploads"),
        checkpointer=make_sqlite_checkpointer(str(tmp / "cp.db")),
        on_event=(lambda sid, ev: events.append((sid, ev))) if events is not None else None,
    )


def default_answer(prompt) -> dict:
    """메인 질문엔 짧게(꼬리질문 유도), 꼬리질문엔 길게 답함."""
    if prompt.type == "await_ready":
        return {"action": "start"}
    if prompt.type == "no_response":
        return {"choice": "skip"}
    text = SHORT if prompt.kind == "main" and prompt.stage == "main" else LONG
    return {"text": text, "answer_duration_sec": 50}


def drive(service: SessionService, sid: str, answer: Callable = default_answer, first=None, limit: int = 200):
    """세션을 끝까지 진행하고 (지나간 prompt 목록, 완료 결과)를 돌려줍니다."""
    prompts = []
    prompt = first or service.start(sid)
    for _ in range(limit):
        prompts.append(prompt)
        res: ActResult = service.act(sid, answer(prompt))
        if res.completed:
            return prompts, res.completed
        prompt = res.prompt
    raise AssertionError("면접이 끝나지 않음")


@pytest.fixture
def service(tmp_path):
    s = make_service(tmp_path)
    yield s
    s.shutdown()


@pytest.fixture
def config() -> SessionConfig:
    return SessionConfig()
