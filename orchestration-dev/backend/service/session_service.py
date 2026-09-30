"""세션 서비스: 그래프 두 개를 묶고, 그래프 밖의 일을 맡습니다.

그래프 밖에서 하는 일
- 동의 확인, 문서 업로드와 삭제
- 백그라운드 평가: 문항이 끝나는 즉시 스레드 풀에서 평가하고 DB 에 저장 (면접 진행을 막지 않음)
- 면접이 끝나면 평가를 모아 그래프에 넘기고 결과 저장
- 중단 후 재개 화면 정보, 만료 세션 정리

FastAPI 는 이 클래스를 얇게 감싸기만 합니다.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import timedelta
from typing import Any, Callable

from langgraph.types import Command
from pydantic import BaseModel

from ..interview import phrases
from ..interview.agents import AnalysisAgents, EvaluationAgents, InterviewAgents
from ..interview.analysis_graph import build_analysis_graph
from ..interview.blueprint import CATEGORY_NAMES, InterviewBlueprint
from ..interview.events import (
    EvaluationBundle,
    InterviewerThinking,
    NoResponseChoice,
    Prompt,
    PromptAdapter,
    QuestionFeedbackReady,
    ResumeStep,
    ResumeView,
    StartSignal,
)
from ..interview.interview_graph import INTRO, build_interview_graph, evaluable_threads
from ..interview.state import (
    CandidateAnswer,
    IntroCheck,
    IntroEvaluation,
    Mode,
    QuestionThread,
    SessionConfig,
    ThreadEvaluation,
)
from ..question_bank.models import QuestionBank
from .consent import ConsentRecord
from .documents import DocKind, DocumentStore
from .store import Store

log = logging.getLogger(__name__)

EventCallback = Callable[[str, BaseModel], None]


class SessionError(Exception):
    """사용자에게 그대로 보여줄 수 있는 오류."""


class TemporaryFailure(Exception):
    """LLM 호출 실패 등 일시적 오류. 같은 요청을 다시 보내면 멈춘 지점부터 이어서 처리합니다."""


class ActResult(BaseModel):
    prompt: Prompt | None = None
    completed: dict | None = None


class SessionService:
    def __init__(
        self,
        bank: QuestionBank,
        analysis_agents: AnalysisAgents,
        interview_agents: InterviewAgents,
        evaluation_agents: EvaluationAgents,
        store: Store,
        documents: DocumentStore,
        checkpointer,
        on_event: EventCallback | None = None,
        max_workers: int = 4,
        eval_timeout_sec: float = 420,  # 패널 최악의 경우: 평가, 검증, 재평가, 재검증 4단계 × 60초 + 대기
        eval_retries: int = 2,
        session_ttl: timedelta = timedelta(hours=24),
    ):
        self.bank = bank
        self.eval_agents = evaluation_agents
        self.store = store
        self.documents = documents
        self.checkpointer = checkpointer
        self.on_event = on_event or (lambda sid, ev: None)
        self.analysis_graph = build_analysis_graph(bank, analysis_agents)
        self.interview_graph = build_interview_graph(bank, interview_agents, checkpointer)
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="eval")
        self.eval_timeout_sec = eval_timeout_sec
        self.eval_retries = eval_retries
        self.session_ttl = session_ttl
        self._futures: dict[str, dict[str, Future]] = defaultdict(dict)
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)

    # ================================================================ 준비 단계

    def create_session(self, consent: ConsentRecord, config: SessionConfig | None = None) -> str:
        config = config or SessionConfig()
        # 동의서에 '비언어 지표는 합불에 쓰지 않는다'고 약속했으므로 서버에서 강제
        rule = config.pass_rule.model_copy(update={"include_nonverbal": False})
        config = config.model_copy(update={"use_camera": consent.camera, "pass_rule": rule})
        sid = uuid.uuid4().hex
        self.store.create_session(sid, consent, config)
        return sid

    def upload_document(self, sid: str, kind: DocKind, filename: str, data: bytes) -> dict:
        row = self._row(sid)
        if not self._consent(row).documents:
            raise SessionError("문서 분석에 동의하지 않아 업로드할 수 없습니다.")
        if row["status"] not in ("created", "analyzed"):
            raise SessionError("면접이 시작된 뒤에는 문서를 올릴 수 없습니다.")
        text = self.documents.save(sid, kind, filename, data)
        if row["status"] == "analyzed":
            self.store.update_session(sid, status="created", blueprint=None)  # 문서가 바뀌면 다시 분석
        return {"kind": kind, "chars": len(text)}

    def analyze(self, sid: str, target_role: str | None = None, seed: int | None = None) -> InterviewBlueprint:
        row = self._row(sid)
        if row["status"] not in ("created", "analyzed"):
            raise SessionError("이미 시작된 면접입니다.")
        texts = self.documents.texts(sid) if self._consent(row).documents else {}
        out = self.analysis_graph.invoke({
            "config": self._config(row), "target_role": target_role, "seed": seed,
            "jd_text": texts.get("jd"), "resume_text": texts.get("resume"), "cover_letter_text": texts.get("cover_letter"),
        })
        bp: InterviewBlueprint = out["blueprint"]
        self.store.update_session(sid, status="analyzed", blueprint=bp, target_role=target_role)
        return bp

    # ================================================================ 면접 진행

    def start(self, sid: str) -> Prompt:
        with self._locks[sid]:
            row = self._row(sid)
            if row["status"] != "analyzed":
                raise SessionError("분석이 끝난 뒤에 시작할 수 있습니다.")
            bp = InterviewBlueprint.model_validate_json(row["blueprint"])
            self.store.update_session(sid, status="in_progress")  # 중복 시작 방지: 먼저 상태 변경
            out = self._invoke(sid, {"session_id": sid, "config": self._config(row), "blueprint": bp})
            return self._prompt_from(out)

    def current_prompt(self, sid: str) -> Prompt | None:
        snap = self.interview_graph.get_state(self._cfg(sid))
        return PromptAdapter.validate_python(snap.interrupts[0].value) if snap.interrupts else None

    def act(self, sid: str, payload: dict[str, Any]) -> ActResult:
        """사용자 행동 하나를 처리합니다. 한 세션의 요청은 순서대로 처리됩니다."""
        with self._locks[sid]:
            row = self._row(sid)
            if row["status"] != "in_progress":
                raise SessionError("진행 중인 면접이 아닙니다.")
            self.store.touch(sid)
            snap = self.interview_graph.get_state(self._cfg(sid))
            if not snap.interrupts and snap.next:
                # 직전 요청이 처리 도중 실패: 이미 받은 입력으로 멈춘 지점부터 이어서 처리하고,
                # 이번 요청의 입력은 쓰지 않음 (같은 답변이 두 번 기록되지 않도록)
                return self._after_step(sid, self._recover(sid))
            prompt = self.current_prompt(sid)
            if prompt is None:
                raise SessionError("대기 중인 질문이 없습니다.")
            if prompt.type == "await_evaluations":
                return self._finish(sid)

            model = {"await_ready": StartSignal, "await_answer": CandidateAnswer, "no_response": NoResponseChoice}[prompt.type]
            resume = model.model_validate(payload)
            if prompt.type == "await_answer":
                if resume.sequence is not None and resume.sequence != prompt.sequence:
                    return ActResult(prompt=prompt)  # 이미 처리된 요청의 재전송: 현재 질문을 다시 알려줌
                self.on_event(sid, InterviewerThinking())

            out = self._invoke(sid, Command(resume=resume.model_dump(mode="json")))
            self._schedule_evaluations(sid)
            return self._after_step(sid, self._prompt_from(out))

    def _after_step(self, sid: str, nxt: Prompt | None) -> ActResult:
        if nxt is not None and nxt.type == "await_evaluations":
            return self._finish(sid)
        return ActResult(prompt=nxt)

    def finish(self, sid: str) -> ActResult:
        """평가 대기에서 멈춘 세션을 마무리 (평가 실패 후 재시도, 재개 시 사용)."""
        with self._locks[sid]:
            prompt = self._recover(sid)
            if prompt is None or prompt.type != "await_evaluations":
                raise SessionError("결과를 정리할 단계가 아닙니다.")
            return self._finish(sid)

    # ================================================================ 백그라운드 평가 (그래프 밖)

    def _schedule_evaluations(self, sid: str) -> None:
        values = self.interview_graph.get_state(self._cfg(sid)).values
        bp: InterviewBlueprint = values["blueprint"]
        done = self.store.evaluations(sid)
        futures = self._futures[sid]
        for th in evaluable_threads(values):
            if th.thread_id not in done and th.thread_id not in futures:
                points = [p for p in values.get("verification_points", {}).values() if p.probed_in == th.thread_id]
                futures[th.thread_id] = self.executor.submit(self._eval_thread, sid, th, bp, points, self._mode(values))
        intro = values["threads"].get(INTRO)
        if intro and intro.closed and any(t.kind == "answer" for t in intro.turns):
            if INTRO not in done and INTRO not in futures:
                futures[INTRO] = self.executor.submit(self._eval_intro, sid, intro, bp, values.get("intro_check"))

    def _retry(self, fn: Callable[[], BaseModel]) -> BaseModel:
        last: Exception | None = None
        for attempt in range(self.eval_retries + 1):
            try:
                return fn()
            except Exception as e:  # LLM 일시 오류 등
                last = e
                log.warning("평가 실패 (%s회차): %s", attempt + 1, e)
        raise RuntimeError(f"평가를 완료하지 못했습니다: {last}")

    def _eval_thread(self, sid: str, th: QuestionThread, bp: InterviewBlueprint, points, mode: Mode) -> ThreadEvaluation:
        ev = self._retry(lambda: self.eval_agents.evaluate_thread(self.bank.get(th.question_id), th, bp, points))
        if not self.store.save_evaluation(sid, th.thread_id, "thread", ev):
            return ev  # 세션이 이미 끝나 삭제됨: 저장하지 않음
        if mode is Mode.PRACTICE:
            self.on_event(sid, QuestionFeedbackReady(thread_id=th.thread_id, evaluation=ev))
        return ev

    def _eval_intro(self, sid: str, intro: QuestionThread, bp: InterviewBlueprint, check: IntroCheck | None) -> IntroEvaluation:
        ev = self._retry(lambda: self.eval_agents.evaluate_intro(intro, bp, check))
        self.store.save_evaluation(sid, INTRO, "intro", ev)
        return ev

    def _collect(self, sid: str, thread_ids: list[str], needs_intro: bool) -> EvaluationBundle:
        """저장된 결과를 우선 쓰고, 진행 중이면 기다리고, 없으면 (서버 재시작 등) 지금 평가합니다."""
        self._schedule_evaluations(sid)
        futures = self._futures[sid]
        for key in [*thread_ids, *([INTRO] if needs_intro else [])]:
            if key in futures:
                futures[key].result(timeout=self.eval_timeout_sec)
        stored = self.store.evaluations(sid)
        missing = [t for t in thread_ids if t not in stored]
        if missing:
            raise RuntimeError(f"평가 결과가 없습니다: {missing}")
        intro = IntroEvaluation.model_validate(stored[INTRO][1]) if needs_intro and INTRO in stored else None
        return EvaluationBundle(
            evaluations={t: ThreadEvaluation.model_validate(stored[t][1]) for t in thread_ids},
            intro_evaluation=intro,
        )

    def _finish(self, sid: str) -> ActResult:
        prompt = self.current_prompt(sid)
        try:
            bundle = self._collect(sid, prompt.thread_ids, prompt.needs_intro_evaluation)
        except Exception as e:
            # 끝난(실패한) 작업만 지워 다음 시도에서 다시 제출. 아직 도는 작업은 그대로 기다림 (중복 호출 방지)
            self._futures[sid] = {k: f for k, f in self._futures[sid].items() if not f.done()}
            raise SessionError(f"결과 정리 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요. ({e})") from e
        self._invoke(sid, Command(resume=bundle.model_dump(mode="json")))
        if self.interview_graph.get_state(self._cfg(sid)).next:
            raise TemporaryFailure("결과 정리가 끝나지 않았습니다. 다시 시도해 주세요.")
        return ActResult(completed=self._finalize(sid))

    # ================================================================ 종료, 저장, 삭제

    def _finalize(self, sid: str) -> dict:
        row = self._row(sid)
        v = self.interview_graph.get_state(self._cfg(sid)).values
        bp: InterviewBlueprint = v["blueprint"]
        threads = list(v["threads"].values())
        answered = [th for th in threads if th.stage == "main" and any(t.kind == "answer" for t in th.turns)]
        summary = {
            "decision": v["chro_decision"].decision,
            "average_score": v["chro_decision"].average_score,
            "target_role": row["target_role"],
            "personalized": bp.personalized,
            "answered_questions": len(answered),
            "total_answer_min": round(v.get("answer_seconds_used", 0) / 60, 1),
            "unasked_categories": [CATEGORY_NAMES[c] for c in v.get("unasked_categories", [])],
        }
        detail = {
            "final_feedback": v["final_feedback"].model_dump(mode="json"),
            "chro_decision": v["chro_decision"].model_dump(mode="json"),
            "evaluations": {k: e.model_dump(mode="json") for k, e in v["evaluations"].items()},
            "intro_evaluation": v["intro_evaluation"].model_dump(mode="json") if v.get("intro_evaluation") else None,
            "observer_report": v["observer_report"].model_dump(mode="json") if v.get("observer_report") else None,
            "time_report": v["time_report"].model_dump(mode="json"),
            "threads": [th.model_dump(mode="json") for th in threads],
            # 문서 원문과 경험 요약은 저장하지 않음. 어떤 문항을 왜 물었는지만 남김
            "plan": [cp.model_dump(mode="json") for cp in bp.plan],
            "company": bp.company.model_dump(mode="json"),
        }
        stored = self._consent(row).store_results
        if stored:
            self.store.save_result(sid, summary, detail)
        self._cleanup(sid, status="completed")
        return {"session_id": sid, "stored": stored, "summary": summary, "detail": detail}

    def _cleanup(self, sid: str, status: str) -> None:
        """문서, 중간 평가, 체크포인트를 지웁니다. 저장 동의한 결과(results)만 남습니다."""
        # 상태를 먼저 바꿔야 실행 중인 평가가 끝나도 저장되지 않음 (save_evaluation 이 상태 확인)
        self.store.update_session(sid, status=status, documents_deleted_at=_iso_now(), blueprint=None)
        for f in self._futures.pop(sid, {}).values():
            f.cancel()
        self.documents.delete_session(sid)
        self.store.delete_evaluations(sid)
        self.checkpointer.delete_thread(sid)

    def abandon(self, sid: str) -> None:
        with self._locks[sid]:
            self._row(sid)
            self._cleanup(sid, status="abandoned")

    def purge_expired(self) -> list[str]:
        """오래된 미완료 세션의 문서와 진행 기록을 지웁니다. 주기적으로 호출하세요."""
        expired = self.store.stale_sessions(self.session_ttl)
        for sid in expired:
            with self._locks[sid]:
                self._cleanup(sid, status="expired")
        return expired

    # ================================================================ 결과 조회

    def list_results(self) -> list[dict]:
        return self.store.results()

    def get_result(self, sid: str) -> dict:
        r = self.store.result(sid)
        if r is None:
            raise SessionError("저장된 결과가 없습니다.")
        return r

    def delete_result(self, sid: str) -> None:
        if not self.store.delete_result(sid):
            raise SessionError("저장된 결과가 없습니다.")

    def in_progress_sessions(self) -> list[dict]:
        return [
            {"session_id": r["id"], "status": r["status"], "updated_at": r["updated_at"], "target_role": r["target_role"]}
            for r in self.store.sessions(["created", "analyzed", "in_progress"])
        ]

    # ================================================================ 중단 후 재개

    def resume_view(self, sid: str) -> ResumeView:
        row = self._row(sid)
        if row["status"] in ("created", "analyzed"):
            steps = [ResumeStep(title="준비 단계로 돌아갑니다",
                                detail="문서 업로드와 분석부터 이어서 진행합니다." if row["status"] == "created"
                                else "분석이 끝난 상태입니다. 면접 구성 안내부터 진행합니다.")]
            return ResumeView(session_id=sid, phase=row["status"], answered_questions=0, answer_minutes_used=0,
                              answer_minutes_left=self._config(row).answer_budget_min, discarded_partial_answer=False,
                              steps=steps, next_prompt=None)
        if row["status"] != "in_progress":
            raise SessionError("이어서 진행할 수 없는 세션입니다. 기록이 만료되었거나 이미 끝난 면접입니다.")

        with self._locks[sid]:
            prompt = self._recover(sid)
        v = self.interview_graph.get_state(self._cfg(sid)).values
        cfg: SessionConfig = v["config"]
        used = v.get("answer_seconds_used", 0.0) / 60
        answered = sum(1 for th in v["threads"].values() if th.stage == "main" and th.closed)
        steps = [
            ResumeStep(title="이전 면접을 이어서 진행합니다",
                       detail=f"본 질문 {answered}개 완료, 답변 시간 {used:.1f}분 사용 (남은 시간 {max(0, cfg.answer_budget_min - used):.1f}분)"),
            ResumeStep(title="카메라와 마이크를 다시 확인합니다",
                       detail="연결이 끊겼다면 장치 권한이 초기화되었을 수 있습니다."),
        ]
        partial = prompt is not None and prompt.type == "await_answer"
        if prompt is None:
            raise SessionError("세션 상태를 확인할 수 없습니다.")
        if prompt.type == "await_ready":
            steps.append(ResumeStep(title="면접 구성 안내부터 다시 봅니다", detail="준비가 되면 면접 시작을 눌러 주세요."))
        elif prompt.type == "await_answer":
            steps.append(ResumeStep(title="중단된 질문을 처음부터 다시 받습니다",
                                    detail="중단될 때 답하던 내용은 저장되지 않았습니다. 같은 질문에 준비시간과 답변시간이 다시 주어집니다."))
            prompt = prompt.model_copy(update={"resumed": True, "lead_in": phrases.RESUME_LEAD_IN})
        elif prompt.type == "no_response":
            steps.append(ResumeStep(title="답변 여부를 선택합니다", detail="다시 답변하거나 다음 질문으로 넘어갈 수 있습니다."))
        else:
            steps.append(ResumeStep(title="면접은 끝났고 결과를 정리합니다", detail="잠시 후 종합 평가와 피드백이 표시됩니다."))
        return ResumeView(
            session_id=sid, phase=v.get("phase", ""), answered_questions=answered,
            answer_minutes_used=round(used, 1), answer_minutes_left=round(max(0.0, cfg.answer_budget_min - used), 1),
            discarded_partial_answer=partial, steps=steps, next_prompt=prompt,
        )

    # ================================================================ 내부

    def _invoke(self, sid: str, value) -> dict:
        try:
            return self.interview_graph.invoke(value, self._cfg(sid))
        except (SessionError, ValueError):
            raise
        except Exception as e:  # LLM 오류 등: 체크포인트는 실패한 노드 직전에 남아 있음
            log.exception("그래프 실행 실패 (%s)", sid)
            raise TemporaryFailure("일시적인 문제로 처리하지 못했습니다. 같은 요청을 다시 보내 주세요.") from e

    def _recover(self, sid: str) -> Prompt | None:
        """노드 실행 중 오류로 멈춘 세션을 멈춘 노드부터 다시 실행합니다."""
        snap = self.interview_graph.get_state(self._cfg(sid))
        if not snap.interrupts and snap.next:
            out = self._invoke(sid, None)
            self._schedule_evaluations(sid)
            return self._prompt_from(out)
        return self.current_prompt(sid)

    def _row(self, sid: str):
        row = self.store.session(sid)
        if row is None:
            raise SessionError("세션을 찾을 수 없습니다.")
        return row

    @staticmethod
    def _consent(row) -> ConsentRecord:
        return ConsentRecord.model_construct(**json.loads(row["consent"]))

    @staticmethod
    def _config(row) -> SessionConfig:
        return SessionConfig.model_validate_json(row["config"])

    @staticmethod
    def _mode(values) -> Mode:
        return values["config"].mode

    @staticmethod
    def _cfg(sid: str) -> dict:
        return {"configurable": {"thread_id": sid}}

    @staticmethod
    def _prompt_from(out: dict) -> Prompt | None:
        if "__interrupt__" in out and out["__interrupt__"]:
            return PromptAdapter.validate_python(out["__interrupt__"][0].value)
        return None

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True)


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
