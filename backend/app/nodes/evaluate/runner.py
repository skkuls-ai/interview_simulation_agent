"""피드백 생성 러너 (담당 E). 마지막 답변과 STT 변환이 모두 끝난 뒤 C 의 평가 단계에서 부른다.

    report = Evaluator(llm).run(EvalInput(session_id, questions, answers, analysis))
    report = evaluate_state(state, llm, on_step)   # graph/ 에서 State 를 그대로 넘길 때

흐름 (A 구조, 9/30 결정)
    1) 태도 측정값을 코드로 계산 (attitude.py)
    2) LLM 호출 4개를 동시에: 태도 조언, 직무 적합성, 답변 일관성, 질문별 피드백(5개를 한 번에)
    3) 코드 검증 (rules.py): 인용 위치, refs, 금지 표현, 근거 없는 판정
    4) 검증 에이전트 1회: 판정이 있는 직무 적합성, 일관성만 검토. 두 호출이 끝나는 즉시 시작해
       질문별 피드백과 시간이 겹치게 한다. 15초 안에 답이 없거나 실패하면 코드 검증 결과로 진행
    5) 무효인 호출만 이유를 넘겨 1회 재평가 → 다시 코드 검증, 검증 에이전트
    6) 남은 문제는 규칙대로 정리 (근거 없는 판정은 WITHHELD), QT- 발급, Report 조립

인식된 답변(transcript_status=DONE)만 LLM 에 넘긴다 (T-215). 시선 값은 태도 프롬프트에만 들어간다 (T-213).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from pydantic import BaseModel

from . import prompts as P
from . import rules as R
from .attitude import attitude_metrics
from ...schemas.state import Analysis, Answer, InterviewState, Question
from .llm.client import JsonLLM, LLMError
from .quotes import QuoteFinder, find_quote

log = logging.getLogger(__name__)

MIN_ANSWERS_FOR_VERDICT = 2  # 인식된 답변이 이보다 적으면 직무 적합성, 일관성은 WITHHELD
NO_ANSWER_NEXT_ACTION = "답변이 기록되지 않았습니다. 마이크 연결을 확인하고 이 질문을 다시 연습해 보세요."
FAILED_NEXT_ACTION = "이 질문의 피드백을 만들지 못했습니다. 답변 내용은 위에서 확인해 주세요."
NO_ADVICE = "답변이 기록되지 않아 말투 조언을 드릴 수 없습니다."

TARGETS = ("attitude", "job_fit", "consistency", "per_question")
VERDICT_TARGETS = ("job_fit", "consistency")  # 검증 에이전트가 보는 대상 (판정이 있는 영역)
ROLE = {"attitude": "coach", "per_question": "coach", "job_fit": "evaluator", "consistency": "evaluator"}


@dataclass
class EvalInput:
    session_id: str
    questions: list[Question]
    answers: list[Answer]
    analysis: Analysis


@dataclass
class Trace:
    """평가 품질 스크립트와 디버깅용 기록. 리포트에는 들어가지 않는다."""

    llm_calls: int = 0
    calls: list[dict] = field(default_factory=list)  # 호출별 대상, 모델, 시작과 끝(실행 시작 기준 초), 토큰
    retried: list[str] = field(default_factory=list)
    issues: dict[str, list[str]] = field(default_factory=dict)
    fallback: list[str] = field(default_factory=list)
    reviewer_failed: bool = False


class Evaluator:
    def __init__(self, llm: JsonLLM, finder: QuoteFinder = find_quote, max_concurrency: int = 4,
                 on_step: Callable[[str, str], None] | None = None, use_reviewer: bool = True):
        self.llm = llm
        self.finder = finder
        self.max_concurrency = max_concurrency
        self.on_step = on_step or (lambda step_id, state: None)
        self.use_reviewer = use_reviewer
        self.trace = Trace()

    # ------------------------------------------------------------ 진입점

    def run(self, inp: EvalInput) -> dict:
        self.trace = Trace()
        self._t0 = time.perf_counter()
        self._lock = threading.Lock()
        ctx = _Context(inp)
        for step in ("attitude", "job_fit", "consistency"):
            self.on_step(step, "RUNNING")

        todo = [t for t in TARGETS if not ctx.skip(t)]
        outs, results, issues = {}, {}, {}
        self._round(ctx, todo, outs, results, issues, feedback=None)

        retry = [t for t in todo if issues[t]]
        if retry:
            self.trace.retried = list(retry)
            first = {t: list(issues[t]) for t in retry}
            self._round(ctx, retry, outs, results, issues, feedback=first)
        self.trace.issues = {t: v for t, v in issues.items() if v}

        report = self._assemble(ctx, results)
        for step in ("attitude", "job_fit", "consistency"):
            self.on_step(step, "DONE")
        self.on_step("compose", "DONE")
        return report

    # ------------------------------------------------------------ LLM 호출과 검증

    def _timed(self, target: str, role: str, system: str, prompt: str, schema, retry: bool):
        start = time.perf_counter() - self._t0
        ok = False
        info = None
        try:
            out, info = self.llm.generate_json(role, system, prompt, schema)
            ok = True
            return out
        finally:
            rec = {"target": target, "retry": retry, "ok": ok, "start": round(start, 1),
                   "end": round(time.perf_counter() - self._t0, 1),
                   "model": getattr(info, "model", None), "attempts": getattr(info, "attempts", None),
                   "input_tokens": getattr(info, "input_tokens", None),
                   "output_tokens": getattr(info, "output_tokens", None)}
            with self._lock:
                self.trace.llm_calls += 1
                self.trace.calls.append(rec)

    def _call(self, ctx: "_Context", target: str, feedback: list[str] | None):
        system, prompt, schema = ctx.request(target, feedback)
        return self._timed(target, ROLE[target], system, prompt, schema, retry=feedback is not None)

    def _round(self, ctx, targets, outs, results, issues, feedback):
        """대상들을 동시에 호출하고, 판정 영역 둘이 끝나면 나머지를 기다리지 않고 바로 검증 에이전트를 부른다."""
        def one(t):
            try:
                out = self._call(ctx, t, (feedback or {}).get(t))
            except LLMError as e:
                return t, None, None, [f"LLM 호출 실패: {str(e)[:80]}"]
            res, iss = ctx.check(t, out, self.finder)
            return t, out, res, iss

        def collect(future):
            t, out, res, iss = future.result()
            outs[t] = out
            issues[t] = iss
            if res is not None:
                results[t] = res

        with ThreadPoolExecutor(max_workers=max(1, min(self.max_concurrency, len(targets)))) as pool:
            futures = {t: pool.submit(one, t) for t in targets}
            verdict = [t for t in VERDICT_TARGETS if t in futures]
            for t in verdict:
                collect(futures[t])
            self._review(ctx, [t for t in verdict if outs.get(t) is not None and not issues[t]], issues)
            for t, f in futures.items():
                if t not in verdict:
                    collect(f)

    def _review(self, ctx, targets, issues):
        if not self.use_reviewer or not targets:
            return
        payload = {t: ctx.last_out[t] for t in targets}
        try:
            out = self._timed("reviewer", "validator", P.REVIEWER_SYSTEM,
                              P.reviewer_prompt(ctx.q_spoken, ctx.answers, payload), P.ReviewOut,
                              retry=bool(self.trace.retried))
        except LLMError as e:  # 검증 에이전트가 실패해도 코드 검증 결과로 진행
            log.warning("검증 에이전트 실패, 코드 검증 결과만 사용: %s", e)
            self.trace.reviewer_failed = True
            return
        for item in out.items:
            if item.target in payload and not item.valid:
                issues[item.target].append(f"검증 에이전트: {item.reason or '무효'}")

    # ------------------------------------------------------------ 조립

    def _assemble(self, ctx: "_Context", results: dict) -> dict:
        self.on_step("compose", "RUNNING")
        n = 0

        def qt(loc: R.Located) -> dict:
            nonlocal n
            n += 1
            return {"quote_id": f"QT-{n:03d}", "question_id": loc.question_id, "text": loc.text,
                    "start": loc.start, "end": loc.end}

        # 태도
        if not ctx.spoken:
            att = R.AttitudeResult(advice=[NO_ADVICE])
        elif "attitude" in results and results["attitude"].advice:
            att = results["attitude"]
        else:
            self.trace.fallback.append("attitude")
            att = R.AttitudeResult(advice=[])
        attitude = {"metrics": ctx.metrics, "advice": att.advice, "quotes": [qt(q) for q in att.quotes]}

        # 직무 적합성, 답변 일관성
        def fit(target: str) -> dict:
            if ctx.skip(target):
                r = R.FitResult("WITHHELD", R.WITHHELD_TOO_FEW)
            elif target in results:
                r = R.finalize_fit(results[target])
            else:
                self.trace.fallback.append(target)
                r = R.FitResult("WITHHELD", R.WITHHELD_FAILED)
            return {"verdict": r.verdict, "reason": r.reason, "quotes": [qt(q) for q in r.quotes], "refs": r.refs}

        job_fit, consistency = fit("job_fit"), fit("consistency")

        # 질문별
        per_q_llm: dict = results.get("per_question", {})
        per_question = []
        for q in ctx.questions:
            cps = [c for c in q.checkpoint_ids if c in ctx.checkpoints]
            linked = [cl for c in cps for cl in ctx.checkpoints[c].claim_ids if cl in ctx.claims]
            if q.question_id not in ctx.spoken:
                item = {"strengths": [], "gaps": [], "next_action": NO_ANSWER_NEXT_ACTION}
            elif q.question_id in per_q_llm:
                o = per_q_llm[q.question_id]
                linked += o.extra_claim_ids
                item = {"strengths": o.strengths, "gaps": o.gaps,
                        "next_action": o.next_action if not R.forbidden(o.next_action) else FAILED_NEXT_ACTION}
            else:
                self.trace.fallback.append(f"per_question:{q.question_id}")
                item = {"strengths": [], "gaps": [], "next_action": FAILED_NEXT_ACTION}
            per_question.append({"question_id": q.question_id, **item,
                                 "linked_claim_ids": list(dict.fromkeys(linked)), "linked_checkpoint_ids": cps})

        # 화면 7 이 다른 API 를 부르지 않도록 참조한 항목만 동봉
        req_ids = set(job_fit["refs"])
        claim_ids = set(consistency["refs"]) | {c for p in per_question for c in p["linked_claim_ids"]}
        cp_ids = {c for p in per_question for c in p["linked_checkpoint_ids"]}
        return {
            "session_id": ctx.session_id,
            "attitude": attitude,
            "job_fit": job_fit,
            "consistency": consistency,
            "per_question": per_question,
            "questions": [{"question_id": q.question_id, "type": P._v(q.type), "text": q.text,
                           "answer_text": ctx.spoken.get(q.question_id)} for q in ctx.questions],
            "requirements": [{"requirement_id": r.requirement_id, "text": r.text, "kind": P._v(r.kind)}
                             for r in sorted(ctx.analysis.requirements, key=lambda r: r.requirement_id)
                             if r.requirement_id in req_ids],  # docs/04 ReportRequirement (PR #10)
            "claims": [{"claim_id": c.claim_id, "text": c.text}
                       for c in sorted(ctx.analysis.claims, key=lambda c: c.claim_id) if c.claim_id in claim_ids],
            "checkpoints": [{"checkpoint_id": c.checkpoint_id, "title": c.title}
                            for c in sorted(ctx.analysis.checkpoints, key=lambda c: c.checkpoint_id)
                            if c.checkpoint_id in cp_ids],
        }


def evaluate_state(state: InterviewState, llm: JsonLLM, on_step: Callable[[str, str], None] | None = None,
                   **kwargs) -> dict:
    """C 의 평가 그래프(graph/)가 부르는 진입점. State 에서 입력을 꺼내 리포트(dict)를 돌려준다.

    돌려준 dict 는 schemas.api.ReportResponse.model_validate() 로 그대로 검증된다.
    분석 결과가 없으면 빈 Analysis 로 진행한다 (직무 적합성, 일관성은 근거 부족으로 WITHHELD 가 되기 쉬움).
    """
    inp = EvalInput(session_id=state.session_id, questions=list(state.questions), answers=list(state.answers),
                    analysis=state.analysis or Analysis())
    return Evaluator(llm, on_step=on_step, **kwargs).run(inp)


class _Context:
    """한 번의 평가에 필요한 입력과 대상별 프롬프트, 검증을 묶는다."""

    def __init__(self, inp: EvalInput):
        self.session_id = inp.session_id
        self.analysis = inp.analysis
        self.questions = sorted(inp.questions, key=lambda q: q.order)
        by_q = {a.question_id: a for a in inp.answers}
        self.answers = by_q
        ordered = [by_q[q.question_id] for q in self.questions if q.question_id in by_q]
        self.metrics = attitude_metrics(ordered)
        self.spoken = {a.question_id: a.transcript for a in ordered
                       if a.transcript_status == "DONE" and a.transcript and a.transcript.strip()}
        self.q_spoken = [q for q in self.questions if q.question_id in self.spoken]
        self.claims = {c.claim_id: c for c in inp.analysis.claims}
        self.checkpoints = {c.checkpoint_id: c for c in inp.analysis.checkpoints}
        self.req_ids = {r.requirement_id for r in inp.analysis.requirements}
        self.last_out: dict[str, BaseModel] = {}

    def skip(self, target: str) -> bool:
        if target in ("job_fit", "consistency"):
            return len(self.spoken) < MIN_ANSWERS_FOR_VERDICT
        return not self.spoken

    def request(self, target: str, feedback: list[str] | None):
        qs, ans = self.q_spoken, self.answers
        if target == "attitude":
            return P.ATTITUDE_SYSTEM, P.attitude_prompt(qs, ans, self.metrics, feedback), P.AttitudeOut
        if target == "job_fit":
            return P.JOB_FIT_SYSTEM, P.job_fit_prompt(qs, ans, self.analysis, feedback), P.FitOut
        if target == "consistency":
            return P.CONSISTENCY_SYSTEM, P.consistency_prompt(qs, ans, self.analysis, feedback), P.FitOut
        return P.PER_QUESTION_SYSTEM, P.per_question_prompt(qs, ans, self.analysis, feedback), P.PerQuestionOut

    def check(self, target: str, out: BaseModel, finder: QuoteFinder):
        self.last_out[target] = out
        if target == "attitude":
            return R.check_attitude(out, self.spoken, finder)
        if target == "job_fit":
            return R.check_fit(out, self.spoken, self.req_ids, finder)
        if target == "consistency":
            return R.check_fit(out, self.spoken, set(self.claims), finder)
        return R.check_per_question(out, list(self.spoken), set(self.claims))
