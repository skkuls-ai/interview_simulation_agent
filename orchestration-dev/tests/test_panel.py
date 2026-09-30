"""평가자 3명 패널: 코드 검증, 검증 에이전트, 재평가, 중앙값, 판단 보류, 동시 호출 제한."""

from __future__ import annotations

import threading
import time

import pytest

from backend.interview.agents import StubAnalysisAgents
from backend.interview.analysis_graph import build_analysis_graph
from backend.interview.evaluation import (
    EvaluationPanel,
    GeminiEvaluator,
    LLMGate,
    PanelEvaluationAgents,
    StubReviewer,
    check_output,
    evidence_in,
)
from backend.interview.prompts.evaluator import EvaluatorOutput, Hit
from backend.interview.state import QuestionThread, SessionConfig, Turn
from backend.llm.client import CallInfo, LLMError
from backend.validators.quote_validator import validate_quotes

from .conftest import BANK, default_answer, drive, full_consent, make_service

Q = BANK.get("Q001")
ANSWER = "출시 3주 전 핵심 개발자가 퇴사했을 때 저는 기능을 필수와 선택으로 나누는 표를 만들어 팀에 제안했습니다."
BP = build_analysis_graph(BANK, StubAnalysisAgents()).invoke({"config": SessionConfig(), "seed": 1})["blueprint"]


def thread(answer=ANSWER) -> QuestionThread:
    return QuestionThread(thread_id="Q001", stage="main", question_id="Q001", category_code="performance",
                          competency_code=Q.competency_code, closed=True,
                          turns=[Turn(speaker="interviewer", kind="main", text=Q.text),
                                 Turn(speaker="candidate", kind="answer", text=answer)])


def out(score=4, quote="기능을 필수와 선택으로 나누는 표를 만들어", cp="Q001-P1", **kw) -> EvaluatorOutput:
    base = dict(positive_hits=[Hit(checkpoint_id=cp, evidence=quote)] if score >= 3 else [],
                negative_hits=[Hit(checkpoint_id="Q001-N1", evidence=quote)] if score <= 2 else [],
                covered_intent_ids=[], verification_results=[], score=score, strengths=["s"], improvements=["i"],
                rationale="r")
    base.update(kw)
    return EvaluatorOutput(**base)


class Scripted:
    """호출될 때마다 준비된 출력을 차례로 돌려주는 평가자."""

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.feedbacks = []

    def evaluate(self, question, thread, bp, points, feedback):
        self.feedbacks.append(feedback)
        o = self.outputs.pop(0)
        if isinstance(o, Exception):
            raise o
        return o


class RejectingReviewer:
    def __init__(self, reject: set[int], once: bool = True):
        self.reject, self.once, self.calls = set(reject), once, []

    def review(self, question, thread, bp, members):
        self.calls.append([i for i, _ in members])
        res = {i: ("점수가 척도와 맞지 않음" if i in self.reject else None) for i, _ in members}
        if self.once:
            self.reject = set()
        return res


def run(evaluators, reviewer=None):
    return EvaluationPanel(evaluators, reviewer or StubReviewer()).evaluate(Q, thread(), BP, [])


# ------------------------------------------------------------------ 코드 검증


def test_evidence_matching_tolerates_spacing_but_not_invention():
    src = "저는 기능을 필수와 선택으로 나누는 표를 만들어 팀에 제안했습니다."
    assert evidence_in("기능을 필수와  선택으로 나누는 표를 만들어,", src)
    assert evidence_in("기능을 필수와 선택으로 나누는 표를 만들었", src)  # 어미 차이 정도는 허용
    assert not evidence_in("매출을 두 배로 늘렸습니다", src)
    assert not evidence_in("표", src)  # 너무 짧은 인용


def test_quote_validator_ignores_fillers_and_issues_source_offsets_and_ids():
    source = "기능을, 음, 필수와 선택으로 나누는 표를 만들어 팀에 제안했습니다."
    quotes = validate_quotes(
        ["기능을 필수와 선택으로 나누는 표를 만들어 팀에 제안했습니다", "매출을 두 배로 늘렸습니다"],
        source,
        "Q001",
    )

    assert len(quotes) == 1
    assert quotes[0].quote_id == "QT-001"
    assert source[quotes[0].start:quotes[0].end] == quotes[0].text
    assert "음" in quotes[0].text


def test_check_output_catches_common_errors():
    th = thread()
    assert check_output(out(), Q, th, []) == []
    assert any("근거가 지원자 발언에 없음" in i for i in check_output(out(quote="매출을 두 배로 늘렸습니다"), Q, th, []))
    assert any("Positive 체크포인트가 아닌" in i for i in check_output(out(cp="Q001-N1"), Q, th, []))
    assert any("근거 있는 Positive" in i for i in check_output(out(score=5, positive_hits=[]), Q, th, []))
    assert any("없는 검증 포인트" in i for i in check_output(
        out(verification_results=[{"point_id": "V9", "result": "supported", "evidence": "x"}]), Q, th, []))


# ------------------------------------------------------------------ 합치기 규칙


def test_all_valid_uses_median():
    ev = run([Scripted(out(4)), Scripted(out(3)), Scripted(out(4))])
    assert ev.score == 4 and ev.status == "ok" and all(m.valid and not m.re_evaluated for m in ev.panel)


def test_disputed_when_gap_two_or_more():
    ev = run([Scripted(out(3)), Scripted(out(3)), Scripted(out(5))])
    assert ev.score == 3 and ev.status == "disputed"


def test_invalid_evaluator_re_evaluated_once_with_feedback():
    bad = Scripted(out(5, quote="지어낸 인용문입니다 정말로"), out(4))
    ev = run([Scripted(out(4)), Scripted(out(4)), bad])
    assert ev.score == 4 and ev.status == "ok"
    assert ev.panel[2].re_evaluated and ev.panel[2].valid
    assert bad.feedbacks[1] and "근거가 지원자 발언에 없음" in bad.feedbacks[1][0]  # 무엇을 고칠지 전달


def test_still_invalid_after_retry_is_dropped_and_two_remaining_are_averaged():
    fake = out(5, quote="지어낸 인용문입니다 정말로")
    ev = run([Scripted(out(3)), Scripted(out(4)), Scripted(fake, fake)])
    assert not ev.panel[2].valid and ev.score == 4  # (3+4)/2 = 3.5 → 반올림 4
    assert ev.status == "ok"


def test_two_invalid_means_undetermined():
    fake = out(5, quote="지어낸 인용문입니다 정말로")
    ev = run([Scripted(out(3)), Scripted(fake, fake), Scripted(LLMError("timeout"), LLMError("timeout"))])
    assert ev.score is None and ev.status == "undetermined"
    assert [m.valid for m in ev.panel] == [True, False, False]


def test_reviewer_rejection_triggers_retry_and_review_of_retried_only():
    reviewer = RejectingReviewer({1})
    ev = run([Scripted(out(4)), Scripted(out(1, negative_hits=[]), out(4)), Scripted(out(4))], reviewer)
    assert ev.panel[1].re_evaluated and ev.panel[1].valid and ev.score == 4
    assert reviewer.calls == [[0, 1, 2], [1]]  # 재평가 뒤에는 다시 채점한 평가자만 검토


def test_reviewer_failure_falls_back_to_code_check():
    class Broken:
        def review(self, *a):
            raise LLMError("503")

    ev = run([Scripted(out(4)), Scripted(out(4)), Scripted(out(5))], Broken())
    assert ev.score == 4 and all(m.valid for m in ev.panel)


def test_gate_limits_concurrent_background_calls():
    active, peak, lock = 0, 0, threading.Lock()

    class SlowLLM:
        def generate_json(self, role, system, prompt, schema):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.1)
            with lock:
                active -= 1
            return out(4), CallInfo(role=role, model="fake", latency_sec=0.1, attempts=1)

    gate = LLMGate(2)
    panel = EvaluationPanel([GeminiEvaluator(SlowLLM(), BANK, gate) for _ in range(3)], StubReviewer())
    ts = [threading.Thread(target=panel.evaluate, args=(Q, thread(), BP, [])) for _ in range(3)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert peak == 2  # 문항 3개 × 평가자 3명이 동시에 돌아도 최대 2개만 호출


# ------------------------------------------------------------------ 세션 연결


def test_undetermined_question_caps_decision_at_hold(tmp_path):
    fake = out(5, quote="지어낸 인용문입니다 정말로")

    class AlwaysFive:
        def evaluate(self, question, thread, bp, points, feedback):
            said = next(t.text for t in thread.turns if t.kind == "answer")
            cp = question.checkpoints.positive[0].id
            return out(5, quote=said[:20], cp=cp)

    class OneBroken(AlwaysFive):
        def __init__(self):
            self.n = 0

        def evaluate(self, question, thread, bp, points, feedback):
            self.n += 1
            if question.id == first_q and self.n:
                return fake.model_copy(update={"positive_hits": [Hit(checkpoint_id=question.checkpoints.positive[0].id,
                                                                     evidence="지어낸 인용문입니다 정말로")]})
            return super().evaluate(question, thread, bp, points, feedback)

    s0 = make_service(tmp_path / "probe")
    sid0 = s0.create_session(full_consent(documents=False))
    first_q = s0.analyze(sid0, seed=1).plan[0].primary[0].question_id
    s0.shutdown()

    panel = EvaluationPanel([AlwaysFive(), OneBroken(), OneBroken()], StubReviewer())
    s = make_service(tmp_path / "run", eval_agents=PanelEvaluationAgents(BANK, panel))
    sid = s.create_session(full_consent(documents=False))
    s.analyze(sid, seed=1)
    _, done = drive(s, sid)
    chro = done["detail"]["chro_decision"]
    assert chro["undetermined_threads"] == [first_q]
    assert chro["decision"] == "hold"  # 나머지는 모두 5점이지만 판단 보류 문항 때문에 최대 보류
    assert done["detail"]["evaluations"][first_q]["score"] is None
    quotes = done["detail"]["final_feedback"]["quotes"]
    assert quotes and len({quote["quote_id"] for quote in quotes}) == len(quotes)
    assert all(quote["quote_id"].startswith("QT-") for quote in quotes)
    s.shutdown()
