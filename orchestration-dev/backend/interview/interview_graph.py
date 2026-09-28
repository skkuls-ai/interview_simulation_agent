"""면접 그래프: 설계도(InterviewBlueprint)를 받아 면접을 진행합니다.

    START → init → await_ready ─→ await_answer ◄───────────────────────────────┐
                   (구성 안내, 준비시간)   │                                         │
                                         ├─ 무응답 → no_response ─(다시)────────────┤
                                         │                     └(넘어가기)→ 문항 종료  │
                                         ├─ 자기소개 → analyze_intro → next_main    │
                                         ├─ 본 질문 → judge ─(꼬리질문, 반복)──────────┘
                                         │                 └(종료)→ next_main ─→ await_answer
                                         │                          (영역 순서, 추가 문항, 시간 예산)
                                         │                          └(모두 끝남)→ closing → await_answer
                                         └─ 마무리 → await_evaluations → observe → chro → feedback → END

멈추는 지점(interrupt) 4곳: await_ready, await_answer, no_response, await_evaluations.
문항 평가는 그래프 밖(세션 서비스)에서 백그라운드로 돌고, 결과는 await_evaluations 에서 한꺼번에 들어옵니다.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from ..question_bank.models import QuestionBank
from . import phrases
from .agents import InterviewAgents
from .blueprint import PlannedQuestion
from .events import (
    EvaluationBundle,
    EvaluationsPending,
    NoResponseChoice,
    NoResponsePrompt,
    QuestionPrompt,
    ReadyPrompt,
    StartSignal,
)
from .state import (
    AnswerQuality,
    CandidateAnswer,
    FollowUpRisk,
    CHRODecision,
    FollowUpDecision,
    InterviewState,
    QuestionThread,
    RuleCheck,
    ThreadEvaluation,
    Turn,
)
from .timing import build_time_report, overtime_of

INTRO, CLOSING = "intro", "closing"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def budget_left_sec(state: InterviewState) -> float:
    return state["config"].answer_budget_min * 60 - state.get("answer_seconds_used", 0.0)


def prompt_count(state: InterviewState) -> int:
    return sum(1 for th in state["threads"].values() for t in th.turns if t.speaker == "interviewer")


def evaluable_threads(state: InterviewState) -> list[QuestionThread]:
    """백그라운드 평가 대상: 답변이 한 번이라도 있는 본 질문 문항."""
    return [
        th for th in state["threads"].values()
        if th.stage == "main" and th.closed and any(t.kind == "answer" for t in th.turns)
    ]


def build_interview_graph(bank: QuestionBank, agents: InterviewAgents, checkpointer=None):
    # ------------------------------------------------------------ 시작

    def init(state: InterviewState) -> dict:
        return {
            "phase": "ready", "category_index": 0, "asked": {}, "threads": {},
            # 검증 포인트는 서류 분석에서 만든 것으로 시작하고, 자기소개에서 새 주장이 나오면 추가
            "verification_points": {p.id: p for p in state["blueprint"].verification_points},
            "answer_seconds_used": 0.0, "unasked_categories": [], "cut_categories": {},
        }

    def await_ready(state: InterviewState) -> dict:
        StartSignal.model_validate(interrupt(ReadyPrompt(guide=state["blueprint"].guide).model_dump(mode="json")))
        intro = QuestionThread(
            thread_id=INTRO, stage="intro",
            turns=[Turn(speaker="interviewer", kind="main", lead_in=phrases.INTRO_LEAD_IN,
                        text=phrases.INTRO_QUESTION, at=_now())],
        )
        return {
            "interview_started_at": _now(),  # 답변 시간은 여기부터가 아니라 문항별 준비시간 종료부터 측정
            "phase": "intro", "active_thread_id": INTRO, "threads": {INTRO: intro},
        }

    # ------------------------------------------------------------ 답변

    def await_answer(state: InterviewState) -> dict:
        cfg = state["config"]
        thread = state["threads"][state["active_thread_id"]]
        q_turn = thread.last_interviewer_turn
        prompt = QuestionPrompt(
            thread_id=thread.thread_id, stage=thread.stage, kind=q_turn.kind, lead_in=q_turn.lead_in,
            text=q_turn.text, sequence=prompt_count(state), think_time_sec=cfg.think_time_sec,
            soft_limit_sec=cfg.answer_soft_limit_sec,
        )
        answer = CandidateAnswer.model_validate(interrupt(prompt.model_dump(mode="json")))

        if not answer.text.strip():
            turn = Turn(speaker="candidate", kind="no_response", text="", at=_now(),
                        answer_duration_sec=answer.answer_duration_sec, vision=answer.vision)
            return {"threads": {thread.thread_id: thread.model_copy(update={"turns": [*thread.turns, turn]})}}

        turn = Turn(
            speaker="candidate", kind="answer", text=answer.text.strip(), at=_now(),
            answer_duration_sec=answer.answer_duration_sec,
            overtime_sec=overtime_of(answer.answer_duration_sec, cfg),
            speech=answer.speech, vision=answer.vision,
        )
        return {
            "threads": {thread.thread_id: thread.model_copy(update={"turns": [*thread.turns, turn]})},
            "answer_seconds_used": state.get("answer_seconds_used", 0.0) + answer.answer_duration_sec,
        }

    def route_after_answer(state: InterviewState):
        thread = state["threads"][state["active_thread_id"]]
        if thread.turns[-1].kind == "no_response":
            return "no_response"
        return {"intro": "analyze_intro", "main": "judge", "closing": "await_evaluations"}[thread.stage]

    def no_response(state: InterviewState) -> dict:
        thread = state["threads"][state["active_thread_id"]]
        choice = NoResponseChoice.model_validate(
            interrupt(NoResponsePrompt(thread_id=thread.thread_id).model_dump(mode="json"))
        )
        if choice.choice == "retry":
            q = thread.last_interviewer_turn
            retry = Turn(speaker="interviewer", kind="repeat", lead_in=phrases.RETRY_LEAD_IN, text=q.text,
                         follow_up_id=q.follow_up_id, verification_point_id=q.verification_point_id, at=_now())
            return {"threads": {thread.thread_id: thread.model_copy(update={"turns": [*thread.turns, retry]})}}
        return {"threads": {thread.thread_id: thread.model_copy(update={"closed": True, "close_reason": "skipped"})}}

    def route_after_no_response(state: InterviewState):
        thread = state["threads"][state["active_thread_id"]]
        if not thread.closed:
            return "await_answer"
        return {"intro": "analyze_intro", "main": "next_main", "closing": "await_evaluations"}[thread.stage]

    # ------------------------------------------------------------ 자기소개

    def analyze_intro(state: InterviewState) -> dict:
        intro = state["threads"][INTRO]
        update = {"threads": {INTRO: intro.model_copy(update={
            "closed": True, "close_reason": intro.close_reason or "single_turn"})}}
        if any(t.kind == "answer" for t in intro.turns):
            existing = list(state.get("verification_points", {}).values())
            check = agents.check_intro(intro, state["blueprint"], existing)
            added = {}
            valid_cats = set(state["config"].category_order)
            for i, p in enumerate(check.verification_points, start=len(existing) + 1):
                cats = [c for c in p.category_codes if c in valid_cats] or ["performance"]
                p = p.model_copy(update={"id": f"V{i}", "source": "intro", "category_codes": cats})
                added[p.id] = p
            update["intro_check"] = check.model_copy(update={"verification_points": list(added.values())})
            update["verification_points"] = added
        return update

    def candidate_context(state: InterviewState) -> str | None:
        """INCONSISTENT 판단용 맥락: 자기소개 답변과 서류의 주요 경험 (짧게)."""
        parts = []
        intro = state["threads"].get(INTRO)
        if intro:
            said = " ".join(t.text for t in intro.turns if t.kind == "answer")
            if said:
                parts.append(f"[자기소개] {said[:400]}")
        exps = state["blueprint"].experiences[:5]
        if exps:
            parts.append("[서류 경험] " + " / ".join(
                f"{e.title}" + (f" (성과: {', '.join(e.claimed_results[:2])})" if e.claimed_results else "") for e in exps))
        return "\n".join(parts) or None

    # ------------------------------------------------------------ 본 질문

    def _next_planned(state: InterviewState) -> tuple[PlannedQuestion | None, bool, int, dict[str, int]]:
        """다음 문항, 추가 문항 여부, 영역 인덱스, 시간 부족으로 못 물은 기본 문항 수."""
        cfg, bp = state["config"], state["blueprint"]
        asked = state.get("asked", {})
        idx = state.get("category_index", 0)
        if budget_left_sec(state) <= 0:
            cut = {}
            for c in cfg.category_order[idx:]:
                done = set(asked.get(c, []))
                left = sum(1 for p in bp.category_plan(c).primary if p.question_id not in done)
                if left:
                    cut[c] = left
            return None, False, idx, cut
        while idx < len(cfg.category_order):
            cat = cfg.category_order[idx]
            cp = bp.category_plan(cat)
            done = set(asked.get(cat, []))
            primary_left = [p for p in cp.primary if p.question_id not in done]
            if primary_left:
                return primary_left[0], False, idx, {}
            cat_threads = [th for th in state["threads"].values() if th.category_code == cat]
            evidence = sum(1 for th in cat_threads if th.evidence_ok)
            extras = sum(1 for th in cat_threads if th.is_extra)
            reserve_left = [p for p in cp.reserve if p.question_id not in done]
            if evidence < cfg.evidence_threshold and extras < cfg.max_extra_per_category and reserve_left:
                return reserve_left[0], True, idx, {}
            idx += 1
        return None, False, idx, {}

    def next_main(state: InterviewState) -> dict:
        pq, is_extra, idx, cut = _next_planned(state)
        if pq is None:
            asked = state.get("asked", {})
            unasked = [c for c in cut if not asked.get(c)]
            closing = QuestionThread(
                thread_id=CLOSING, stage="closing",
                turns=[Turn(speaker="interviewer", kind="main", lead_in=phrases.CLOSING_LEAD_IN,
                            text=phrases.CLOSING_QUESTION, at=_now())],
            )
            return {"phase": "closing", "category_index": idx, "unasked_categories": unasked, "cut_categories": cut,
                    "active_thread_id": CLOSING, "threads": {CLOSING: closing}}

        q = bank.get(pq.question_id)
        first_main = not any(th.stage == "main" for th in state["threads"].values())
        lead_in = phrases.FIRST_MAIN_LEAD_IN if first_main else phrases.pick(phrases.NEXT_MAIN_LEAD_INS, prompt_count(state))
        thread = QuestionThread(
            thread_id=q.id, stage="main", question_id=q.id, category_code=pq.category_code,
            competency_code=pq.competency_code, is_extra=is_extra,
            turns=[Turn(speaker="interviewer", kind="main", lead_in=lead_in, text=pq.personalized_text or q.text, at=_now())],
        )
        asked = {k: list(v) for k, v in state.get("asked", {}).items()}
        asked.setdefault(pq.category_code, []).append(q.id)
        return {"phase": "interviewing", "category_index": idx, "asked": asked,
                "active_thread_id": q.id, "threads": {q.id: thread}}

    def judge(state: InterviewState) -> dict:
        cfg = state["config"]
        thread = state["threads"][state["active_thread_id"]]
        q = bank.get(thread.question_id)
        at_limit = thread.follow_up_count >= cfg.max_follow_ups
        planned = next((pq for cp in state["blueprint"].plan for pq in cp.primary + cp.reserve
                        if pq.question_id == thread.question_id), None)
        assigned = set(planned.verification_point_ids) if planned else set()
        points = [
            p for p in state.get("verification_points", {}).values()
            if p.status == "pending" and (p.id in assigned or thread.category_code in p.category_codes)
        ]
        update: dict = {}

        repeats = sum(1 for t in thread.turns if t.kind == "repeat")
        forced = "budget_exhausted" if budget_left_sec(state) <= 0 else None
        if forced:
            decision = FollowUpDecision(action="close", rationale="강제 종료: 답변 시간 예산 소진")
        else:
            # 한도에 도달해도 마지막 답변의 근거 충분 여부는 판단해야 추가 문항 결정이 정확함
            decision = agents.decide_follow_up(q, thread, cfg, points, state["blueprint"],
                                               candidate_context=candidate_context(state))
            if decision.action == "repeat_question" and repeats >= cfg.max_repeats_per_question:
                decision = decision.model_copy(update={"action": "close", "evidence_sufficient": False,
                                                       "quality": AnswerQuality.PARTIAL,
                                                       "rationale": decision.rationale + " (반복 요청 한도 초과)"})

        turns = list(thread.turns)
        closed, reason, quality = False, None, None
        n = prompt_count(state)
        if decision.action == "repeat_question":
            last = thread.last_interviewer_turn
            turns.append(Turn(speaker="interviewer", kind="repeat", lead_in=phrases.REPEAT_LEAD_IN, text=last.text,
                              follow_up_id=last.follow_up_id, verification_point_id=last.verification_point_id, at=_now()))
        elif decision.action == "ask_follow_up" and not at_limit:
            lead_in = phrases.pick(phrases.FOLLOW_UP_LEAD_INS, n)
            if decision.follow_up_id:
                fu = next(f for f in q.follow_ups if f.id == decision.follow_up_id)
                text = f"{fu.note}, {fu.text}" if fu.kind and fu.kind.value == "role_play" else fu.text
                turns.append(Turn(speaker="interviewer", kind="follow_up", lead_in=lead_in, text=text,
                                  follow_up_id=fu.id, verification_point_id=decision.verification_point_id, at=_now()))
            else:
                turns.append(Turn(speaker="interviewer", kind="generated_follow_up", lead_in=lead_in,
                                  text=decision.generated_question or "", verification_point_id=decision.verification_point_id,
                                  at=_now()))
            if decision.verification_point_id in state.get("verification_points", {}):
                p = state["verification_points"][decision.verification_point_id]
                update["verification_points"] = {p.id: p.model_copy(update={"status": "probed", "probed_in": thread.thread_id})}
        else:
            closed = True
            if forced:
                reason = forced  # 판단 없이 닫힘: 품질 표시 없음
            elif decision.action == "ask_follow_up":
                reason = "max_follow_ups"  # 더 묻고 싶었지만 한도 도달 = 근거 부족
                q_label = decision.quality
                quality = q_label if q_label and q_label is not AnswerQuality.SUFFICIENT else AnswerQuality.PARTIAL
            else:
                quality = decision.quality
                ok = quality is AnswerQuality.SUFFICIENT if quality else decision.evidence_sufficient
                reason = "sufficient" if ok else "insufficient"

        update["threads"] = {thread.thread_id: thread.model_copy(update={
            "turns": turns, "decisions": [*thread.decisions, decision], "closed": closed, "close_reason": reason,
            "quality": quality, "inconsistency_note": decision.inconsistency_note if closed else None})}
        return update

    def route_after_judge(state: InterviewState):
        return "next_main" if state["threads"][state["active_thread_id"]].closed else "await_answer"

    # ------------------------------------------------------------ 종료와 평가

    def await_evaluations(state: InterviewState) -> dict:
        closing = state["threads"].get(CLOSING)
        update: dict = {"phase": "evaluating"}
        if closing and not closing.closed:
            closing = closing.model_copy(update={"closed": True, "close_reason": "single_turn"})
            update["threads"] = {CLOSING: closing}

        targets = evaluable_threads(state)
        intro = state["threads"].get(INTRO)
        needs_intro = bool(intro and any(t.kind == "answer" for t in intro.turns))
        bundle = EvaluationBundle.model_validate(interrupt(EvaluationsPending(
            thread_ids=[th.thread_id for th in targets], needs_intro_evaluation=needs_intro,
        ).model_dump(mode="json")))

        missing = {th.thread_id for th in targets} - set(bundle.evaluations)
        if missing:
            raise ValueError(f"평가 결과 누락: {sorted(missing)}")
        evaluations = dict(bundle.evaluations)
        # 무응답으로 넘긴 본 질문은 1점 처리 (근거 없음)
        for th in state["threads"].values():
            if th.stage == "main" and th.closed and not any(t.kind == "answer" for t in th.turns):
                evaluations[th.thread_id] = ThreadEvaluation(
                    thread_id=th.thread_id, question_id=th.question_id, competency_code=th.competency_code,
                    score=1, confidence=1.0, improvements=["질문에 답변하지 않았습니다."],
                )
        update["evaluations"] = evaluations
        if bundle.intro_evaluation:
            update["intro_evaluation"] = bundle.intro_evaluation
        return update

    def observe(state: InterviewState) -> dict:
        threads = list(state["threads"].values())
        has_metrics = any(t.speech or t.vision for th in threads for t in th.turns)
        return {"observer_report": agents.observe(threads)} if has_metrics else {}

    def chro(state: InterviewState) -> dict:
        rule = state["config"].pass_rule
        all_evals = list(state["evaluations"].values())
        undetermined = [e.thread_id for e in all_evals if e.score is None]
        disputed = [e.thread_id for e in all_evals if e.status == "disputed"]
        evals = [e for e in all_evals if e.score is not None]  # 판단 보류 문항은 점수 계산에서 제외
        inconsistent = [th.thread_id for th in state["threads"].values() if th.quality is AnswerQuality.INCONSISTENT]
        cat_of = {th.thread_id: th.category_code for th in state["threads"].values()}
        by_comp, by_cat = defaultdict(list), defaultdict(list)
        for e in evals:
            by_comp[e.competency_code].append(e.score)
            by_cat[cat_of.get(e.thread_id)].append(e.score)
        comp_scores = {k: round(sum(v) / len(v), 2) for k, v in by_comp.items()}
        cat_scores = {k: round(sum(v) / len(v), 2) for k, v in by_cat.items() if k}
        avg = round(sum(e.score for e in evals) / len(evals), 2) if evals else 0.0
        obs = state.get("observer_report")
        if rule.include_nonverbal and obs and obs.nonverbal_score is not None and evals:
            avg = round((avg * len(evals) + obs.nonverbal_score) / (len(evals) + 1), 2)

        unasked = state.get("unasked_categories", [])
        weakest = min(comp_scores.items(), key=lambda kv: kv[1]) if comp_scores else ("-", 0.0)
        checks = [
            RuleCheck(name="평균 점수", passed=avg >= rule.min_average if evals else True,
                      detail=f"{avg} / 기준 {rule.min_average}" if evals else "해당 없음 (모든 문항 판단 보류)"),
            RuleCheck(name="역량 과락", passed=weakest[1] >= rule.min_each_competency if evals else True,
                      detail=f"최저 {weakest[0]} {weakest[1]} / 기준 {rule.min_each_competency}" if evals
                      else "해당 없음 (모든 문항 판단 보류)"),
            RuleCheck(name="영역 평가 완료", passed=not unasked,
                      detail="모든 영역 평가" if not unasked else f"미평가 영역: {', '.join(unasked)}"),
            RuleCheck(name="답변 일관성", passed=not inconsistent,
                      detail="모순된 답변 없음" if not inconsistent else f"모순된 답변: {', '.join(inconsistent)} (최대 보류)"),
            RuleCheck(name="판단 보류 문항", passed=not undetermined,
                      detail="없음" if not undetermined else f"평가자 합의 불가: {', '.join(undetermined)} (최대 보류)"),
        ]
        if not evals and undetermined:
            decision = "hold"  # 지원자 탓이 아니라 평가가 성립하지 않은 경우
        elif not evals or not checks[1].passed:
            decision = "fail"
        elif abs(avg - rule.min_average) <= rule.hold_margin:
            decision = "hold"
        else:
            decision = "pass" if avg > rule.min_average else "fail"
        if unasked:
            if rule.unasked_category_policy == "fail":
                decision = "fail"
            elif decision == "pass":
                decision = "hold"
        if (inconsistent or undetermined) and decision == "pass":
            decision = "hold"

        draft = CHRODecision(decision=decision, average_score=avg, competency_scores=comp_scores,
                             category_scores=cat_scores, unasked_categories=unasked,
                             inconsistent_threads=inconsistent, undetermined_threads=undetermined,
                             disputed_threads=disputed, rule_checks=checks, rationale="")
        return {"chro_decision": draft.model_copy(update={"rationale": agents.chro_rationale(draft, evals)})}

    def feedback(state: InterviewState) -> dict:
        report = build_time_report(
            list(state["threads"].values()), state["config"], state.get("answer_seconds_used", 0.0),
            state.get("unasked_categories", []), state.get("cut_categories", {}),
        )
        fb = agents.final_feedback(
            state["chro_decision"], list(state["evaluations"].values()), state.get("intro_evaluation"),
            state.get("observer_report"), report,
        )
        # 시간 리포트, 모순 답변, 품질 분포는 LLM 출력과 무관하게 코드가 계산한 값으로 넣음
        threads = list(state["threads"].values())
        risks = [
            FollowUpRisk(
                thread_id=th.thread_id, question_text=th.turns[0].text,
                note=th.inconsistency_note or (th.decisions[-1].rationale if th.decisions else "앞뒤 내용이 맞지 않음"),
                tip="다음 면접에서 이 부분을 다시 물을 가능성이 높습니다. 서류, 자기소개, 답변 사이의 사실관계"
                    "(기간, 본인 역할, 수치)를 하나로 맞춰 두고, 왜 달라 보였는지 설명할 준비를 하세요.",
            )
            for th in threads if th.quality is AnswerQuality.INCONSISTENT
        ]
        quality_counts: dict[str, int] = {}
        for th in threads:
            if th.stage == "main" and th.quality:
                quality_counts[th.quality.value] = quality_counts.get(th.quality.value, 0) + 1
        fb = fb.model_copy(update={"time_management": report, "intro_feedback": state.get("intro_evaluation"),
                                   "follow_up_risks": risks, "answer_quality": quality_counts})
        return {"time_report": report, "final_feedback": fb, "phase": "done"}

    # ------------------------------------------------------------ 조립

    g = StateGraph(InterviewState)
    for name, fn in [
        ("init", init), ("await_ready", await_ready), ("await_answer", await_answer), ("no_response", no_response),
        ("analyze_intro", analyze_intro), ("next_main", next_main), ("judge", judge),
        ("await_evaluations", await_evaluations), ("observe", observe), ("chro", chro), ("feedback", feedback),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "init")
    g.add_edge("init", "await_ready")
    g.add_edge("await_ready", "await_answer")
    g.add_conditional_edges("await_answer", route_after_answer,
                            ["no_response", "analyze_intro", "judge", "await_evaluations"])
    g.add_conditional_edges("no_response", route_after_no_response,
                            ["await_answer", "analyze_intro", "next_main", "await_evaluations"])
    g.add_edge("analyze_intro", "next_main")
    g.add_edge("next_main", "await_answer")
    g.add_conditional_edges("judge", route_after_judge, ["await_answer", "next_main"])
    g.add_edge("await_evaluations", "observe")
    g.add_edge("observe", "chro")
    g.add_edge("chro", "feedback")
    g.add_edge("feedback", END)
    return g.compile(checkpointer=checkpointer)
