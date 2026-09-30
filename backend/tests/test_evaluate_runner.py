"""평가 러너 테스트. 가짜 LLM 으로 흐름과 코드 판정 규칙을 확인한다 (API 호출 없음).

기준 입력은 mock/build_report_mock.py 의 데모 시나리오를 그대로 쓴다. 가짜 LLM 이 mock 문구를 돌려주면
러너 결과가 report.json 과 같아야 한다 (mock 과 실제 코드가 같은 모양이라는 확인).
"""

import importlib.util
import json
import threading
import time
from pathlib import Path

import pytest

from app.nodes.evaluate import prompts as P
from app.schemas.state import Analysis, Answer, Checkpoint, Claim, DeliveryMetrics, Question, Requirement
from app.nodes.evaluate.llm.client import LLMError
from app.nodes.evaluate.runner import EvalInput, Evaluator

MOCK_DIR = Path(__file__).parents[2] / "shared" / "mock"
spec = importlib.util.spec_from_file_location("mockbuild", Path(__file__).parents[1] / "scripts" / "build_report_mock.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

CHECKPOINT_CLAIMS = {"CP-001": ["CL-001", "CL-002"], "CP-002": ["CL-003", "CL-004"], "CP-004": ["CL-006", "CL-007"]}
QUESTION_CPS = {"Q-1": ["CP-001"], "Q-3": ["CP-004"], "Q-4": ["CP-001", "CP-002"]}
ORDER = {"Q-1": 1, "Q-2": 2, "Q-3": 3, "Q-4": 4, "Q-5": 5}


def analysis() -> Analysis:
    return Analysis(
        requirements=[Requirement(**r) for r in M.REQUIREMENTS],
        claims=[Claim(**c) for c in M.CLAIMS],
        checkpoints=[Checkpoint(checkpoint_id=c["checkpoint_id"], title=c["title"], what_to_verify="",
                                claim_ids=CHECKPOINT_CLAIMS[c["checkpoint_id"]])
                     for c in M.CHECKPOINTS],
    )


def make_input(qa=None) -> EvalInput:
    qa = qa or M.QA
    questions = [Question(question_id=q["question_id"], order=ORDER[q["question_id"]], type=q["type"], text=q["text"],
                          checkpoint_ids=QUESTION_CPS.get(q["question_id"], []), criteria=["(테스트)"]) for q in qa]
    answers = [Answer(question_id=q["question_id"], transcript=q["answer_text"],
                      transcript_status="DONE" if q["answer_text"] else "NO_SPEECH",
                      duration_sec=q["duration_sec"], timed_out=q["timed_out"],
                      delivery=DeliveryMetrics(**q["delivery"]) if q["delivery"] else None) for q in qa]
    return EvalInput(M.SESSION_ID, questions, answers, analysis())


def ref(qid, text):
    return {"question_id": qid, "text": text}


def mock_outputs() -> dict:
    """mock 문구를 LLM 출력 모양으로 바꾼 것. 대상별 기본 응답."""
    return {
        "attitude": P.AttitudeOut(advice=[{"text": t, "quotes": [ref(*q) for q in qs]} for t, qs in M.ATTITUDE_ADVICE]),
        "job_fit": P.FitOut(verdict=M.JOB_FIT["verdict"], reason=M.JOB_FIT["reason"],
                            quotes=[ref(*q) for q in M.JOB_FIT["quotes"]], refs=M.JOB_FIT["refs"]),
        "consistency": P.FitOut(verdict=M.CONSISTENCY["verdict"], reason=M.CONSISTENCY["reason"],
                                quotes=[ref(*q) for q in M.CONSISTENCY["quotes"]], refs=M.CONSISTENCY["refs"]),
        "per_question": P.PerQuestionOut(items=[
            {"question_id": qid, "strengths": v["strengths"], "gaps": v["gaps"], "next_action": v["next_action"],
             "extra_claim_ids": [c for c in v["linked_claim_ids"]
                                 if c not in {cl for cp in QUESTION_CPS.get(qid, []) for cl in CHECKPOINT_CLAIMS[cp]}]}
            for qid, v in M.PER_QUESTION.items()]),
    }


def target_of(system: str) -> str:
    return {P.ATTITUDE_SYSTEM: "attitude", P.JOB_FIT_SYSTEM: "job_fit", P.CONSISTENCY_SYSTEM: "consistency",
            P.PER_QUESTION_SYSTEM: "per_question", P.REVIEWER_SYSTEM: "reviewer"}[system]


class FakeLLM:
    """대상별로 준비한 응답을 차례로 돌려준다. 응답이 예외면 던진다. 호출 기록을 남긴다."""

    def __init__(self, scripted: dict | None = None, review=None, delay: float = 0.0, delays: dict | None = None):
        base = mock_outputs()
        self.scripted = {t: list((scripted or {}).get(t, [base[t]])) for t in base}
        self.review = review  # None: 모두 유효, 함수(targets)->ReviewOut, 또는 예외
        self.calls: list[tuple[str, str]] = []
        self.prompts: dict[str, list[str]] = {}
        self.delay, self.delays, self.active, self.max_active = delay, delays or {}, 0, 0
        self.lock = threading.Lock()

    def generate_json(self, role, system, prompt, schema):
        t = target_of(system)
        with self.lock:
            self.calls.append((role, t))
            self.prompts.setdefault(t, []).append(prompt)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delays.get(t, self.delay))
            if t == "reviewer":
                targets = list(json.loads(prompt.split("## 검토할 피드백\n", 1)[1]))
                if isinstance(self.review, Exception):
                    raise self.review
                out = self.review(targets) if self.review else P.ReviewOut(
                    items=[{"target": x, "valid": True, "reason": ""} for x in targets])
                return out, None
            queue = self.scripted[t]
            out = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(out, Exception):
                raise out
            return out, None
        finally:
            with self.lock:
                self.active -= 1

    def count(self, target):
        return sum(1 for _, t in self.calls if t == target)


def with_(model, **update):
    """검증을 거친 사본 (model_copy 는 중첩 모델을 검증하지 않음)."""
    return type(model).model_validate({**model.model_dump(), **update})


def run(llm, qa=None, **kw):
    ev = Evaluator(llm, **kw)
    return ev.run(make_input(qa)), ev


# ------------------------------------------------------------------ 정상 흐름


def test_report_equals_mock_when_llm_returns_mock_text():
    report, ev = run(FakeLLM())
    expected = json.loads((MOCK_DIR / "report.json").read_text(encoding="utf-8"))
    assert report == expected
    assert ev.trace.llm_calls == 5 and not ev.trace.retried  # 4개 + 검증 1회


def test_four_calls_run_in_parallel_then_one_review():
    llm = FakeLLM(delay=0.05)
    run(llm)
    assert llm.max_active == 4
    assert [t for _, t in llm.calls[-1:]] == ["reviewer"] and llm.calls[-1][0] == "validator"
    roles = {t: role for role, t in llm.calls}
    assert roles == {"job_fit": "evaluator", "consistency": "evaluator", "attitude": "coach",
                     "per_question": "coach", "reviewer": "validator"}


def test_reviewer_sees_only_verdict_areas():
    llm = FakeLLM()
    run(llm)
    reviewed = json.loads(llm.prompts["reviewer"][0].split("## 검토할 피드백\n", 1)[1])
    assert set(reviewed) == {"job_fit", "consistency"}


def test_reviewer_overlaps_slow_per_question_call():
    llm = FakeLLM(delays={"job_fit": 0.02, "consistency": 0.02, "attitude": 0.02, "per_question": 0.3, "reviewer": 0.05})
    _, ev = run(llm)
    c = {x["target"]: x for x in ev.trace.calls}
    assert c["reviewer"]["start"] < c["per_question"]["end"]  # 질문별 피드백을 기다리지 않고 검증 시작
    assert c["reviewer"]["start"] >= max(c["job_fit"]["end"], c["consistency"]["end"]) - 0.01


def test_steps_are_reported():
    seen = []
    Evaluator(FakeLLM(), on_step=lambda s, st: seen.append((s, st))).run(make_input())
    assert ("job_fit", "RUNNING") in seen and ("compose", "DONE") == seen[-1]


# ------------------------------------------------------------------ 인용 (T-201, T-202)


def test_invented_quote_triggers_one_retry_with_feedback():
    base = mock_outputs()["job_fit"]
    bad = with_(base, quotes=[ref("Q-4", "매출을 두 배로 늘렸다고 말했습니다")])
    llm = FakeLLM({"job_fit": [bad, base]})
    report, ev = run(llm)
    assert ev.trace.retried == ["job_fit"] and llm.count("job_fit") == 2
    assert "인용이 답변 원문에 없음" in llm.prompts["job_fit"][1]  # 무엇을 고칠지 전달
    assert report["job_fit"]["verdict"] == "NEEDS_WORK"


def test_quotes_positions_match_answer_text():
    report, _ = run(FakeLLM())
    answers = {q["question_id"]: q["answer_text"] for q in report["questions"]}
    quotes = report["attitude"]["quotes"] + report["job_fit"]["quotes"] + report["consistency"]["quotes"]
    assert [q["quote_id"] for q in quotes] == [f"QT-{i:03d}" for i in range(1, len(quotes) + 1)]
    assert all(answers[q["question_id"]][q["start"]:q["end"]] == q["text"] for q in quotes)


def test_verdict_without_evidence_becomes_withheld_after_retry():
    bad = with_(mock_outputs()["consistency"], quotes=[ref("Q-1", "지어낸 문장입니다 정말로")])
    report, ev = run(FakeLLM({"consistency": [bad, bad]}))
    c = report["consistency"]
    assert c["verdict"] == "WITHHELD" and c["quotes"] == [] and "판단을 보류" in c["reason"]


# ------------------------------------------------------------------ refs (T-203), 금지 표현 (T-013)


def test_unknown_refs_are_dropped():
    bad = with_(mock_outputs()["job_fit"], refs=["RQ-014", "RQ-999"])
    report, ev = run(FakeLLM({"job_fit": [bad, bad]}))
    assert report["job_fit"]["refs"] == ["RQ-014"]
    assert any("RQ-999" in i for i in ev.trace.issues["job_fit"])


def test_forbidden_words_in_reason_retry_then_withheld():
    bad = with_(mock_outputs()["job_fit"], reason="자신감이 부족해 보입니다.")
    report, _ = run(FakeLLM({"job_fit": [bad, bad]}))
    assert report["job_fit"]["verdict"] == "WITHHELD" and "자신감" not in json.dumps(report, ensure_ascii=False)


def test_forbidden_advice_is_dropped():
    out = P.AttitudeOut(advice=[{"text": "긴장한 것처럼 들립니다."}, {"text": "결론부터 말해 보세요."}])
    report, _ = run(FakeLLM({"attitude": [out, out]}))
    assert report["attitude"]["advice"] == ["결론부터 말해 보세요."]


# ------------------------------------------------------------------ 인식 실패 (T-215), 판정 가능 답변 수


def edge_qa():
    qa = [dict(q) for q in M.QA]
    qa[2] = {**qa[2], "answer_text": None}  # Q-3 인식 실패
    return qa


def test_unrecognized_answer_is_not_sent_to_llm_and_gets_template():
    llm = FakeLLM({"per_question": [P.PerQuestionOut(items=[i for i in mock_outputs()["per_question"].items
                                                            if i.question_id != "Q-3"])]})
    report, _ = run(llm, qa=edge_qa())
    q3_text = M.QA[2]["answer_text"][:20]
    assert all(q3_text not in p for ps in llm.prompts.values() for p in ps)
    q3 = next(p for p in report["per_question"] if p["question_id"] == "Q-3")
    assert q3["strengths"] == [] and "기록되지 않았습니다" in q3["next_action"]
    assert q3["linked_checkpoint_ids"] == ["CP-004"]  # 연결 정보는 유지
    assert next(q for q in report["questions"] if q["question_id"] == "Q-3")["answer_text"] is None


def test_fewer_than_two_answers_withholds_without_llm_call():
    qa = [{**q, "answer_text": None} if q["question_id"] != "Q-2" else dict(q) for q in M.QA]
    llm = FakeLLM({"per_question": [P.PerQuestionOut(items=[i for i in mock_outputs()["per_question"].items
                                                            if i.question_id == "Q-2"])],
                   "attitude": [P.AttitudeOut(advice=[{"text": "결론부터 말해 보세요."}])]})
    report, _ = run(llm, qa=qa)
    assert llm.count("job_fit") == 0 and llm.count("consistency") == 0
    assert report["job_fit"]["verdict"] == report["consistency"]["verdict"] == "WITHHELD"


def test_no_recognized_answers_at_all():
    qa = [{**q, "answer_text": None} for q in M.QA]
    llm = FakeLLM()
    report, ev = run(llm, qa=qa)
    assert ev.trace.llm_calls == 0
    assert report["attitude"]["advice"] and report["attitude"]["metrics"]["speech"]["words_per_min"] is None


# ------------------------------------------------------------------ 시선 (T-213)


def test_gaze_values_only_in_attitude_prompt():
    llm = FakeLLM()
    run(llm)
    for t in ("job_fit", "consistency", "per_question"):
        assert all("frontal_ratio" not in p and "gaze" not in p for p in llm.prompts[t])
    assert "frontal_ratio" in llm.prompts["attitude"][0]


def test_gaze_change_does_not_change_verdicts():
    qa_low = [{**q, "delivery": {"measurable": True, "frontal_ratio": 0.1, "gaze_away_count": 30}} for q in M.QA]
    a, _ = run(FakeLLM())
    b, _ = run(FakeLLM(), qa=qa_low)
    for area in ("job_fit", "consistency"):
        assert a[area] == b[area]
    assert a["per_question"] == b["per_question"]


# ------------------------------------------------------------------ 검증 에이전트, 실패 처리


def test_reviewer_rejection_retries_only_that_target():
    def review(targets):
        return P.ReviewOut(items=[{"target": t, "valid": t != "consistency" or review.n > 0, "reason": "근거 왜곡"}
                                  for t in targets])
    review.n = 0

    class Counting(FakeLLM):
        def generate_json(self, role, system, prompt, schema):
            out = super().generate_json(role, system, prompt, schema)
            if target_of(system) == "reviewer":
                review.n += 1
            return out

    llm = Counting(review=review)
    _, ev = run(llm)
    assert ev.trace.retried == ["consistency"] and llm.count("consistency") == 2 and llm.count("job_fit") == 1
    assert llm.count("reviewer") == 2
    second = json.loads(llm.prompts["reviewer"][1].split("## 검토할 피드백\n", 1)[1])
    assert set(second) == {"consistency"}  # 재평가 뒤에는 다시 쓴 영역만 검토


def test_reviewer_failure_falls_back_to_code_check():
    report, ev = run(FakeLLM(review=LLMError("503")))
    assert ev.trace.reviewer_failed and report["job_fit"]["verdict"] == "NEEDS_WORK"


def test_llm_failure_twice_uses_fallback():
    llm = FakeLLM({"job_fit": [LLMError("timeout"), LLMError("timeout")],
                   "per_question": [LLMError("timeout"), LLMError("timeout")]})
    report, ev = run(llm)
    assert report["job_fit"]["verdict"] == "WITHHELD" and "job_fit" in ev.trace.fallback
    assert all(p["next_action"] and p["strengths"] == [] for p in report["per_question"])
    assert report["consistency"]["verdict"] == "NEEDS_WORK"  # 다른 영역은 영향 없음


def test_per_question_missing_item_retries_then_fills_template():
    items = [i for i in mock_outputs()["per_question"].items if i.question_id != "Q-5"]
    llm = FakeLLM({"per_question": [P.PerQuestionOut(items=items)] * 2})
    report, ev = run(llm)
    assert ev.trace.retried == ["per_question"]
    q5 = next(p for p in report["per_question"] if p["question_id"] == "Q-5")
    assert q5["strengths"] == [] and q5["next_action"]


def test_attitude_has_no_verdict_or_score():
    report, _ = run(FakeLLM())
    assert set(report["attitude"]) == {"metrics", "advice", "quotes"}  # T-214


def test_trace_records_each_call_with_timing():
    _, ev = run(FakeLLM(delay=0.02))
    targets = sorted(c["target"] for c in ev.trace.calls)
    assert targets == ["attitude", "consistency", "job_fit", "per_question", "reviewer"]
    review = next(c for c in ev.trace.calls if c["target"] == "reviewer")
    verdict = [c for c in ev.trace.calls if c["target"] in ("job_fit", "consistency")]
    assert all(c["ok"] and c["end"] >= c["start"] for c in ev.trace.calls)
    assert review["start"] >= max(c["end"] for c in verdict) - 0.05  # 검증은 판정 영역 둘이 끝난 뒤


# ------------------------------------------------------------------ LLM 클라이언트: 429 대기, 역할 설정


def test_rate_limited_call_waits_then_retries(monkeypatch):
    pytest.importorskip("google.genai")
    from app.nodes.evaluate.llm import client as C
    from app.nodes.evaluate.llm.settings import LLMSettings

    class Resp:
        text = '{"items": []}'
        usage_metadata = None

    class Models:
        def __init__(self):
            self.n = 0

        def generate_content(self, **kw):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            return Resp()

    class Fake:
        models = Models()

    slept = []
    monkeypatch.setattr(C.time, "sleep", lambda s: slept.append(s))
    cli = C.GeminiClient(LLMSettings(project="p"), client=Fake())
    out, info = cli.generate_json("coach", "sys", "prompt", P.ReviewOut)
    assert info.attempts == 2 and slept == [C.RATE_LIMIT_WAIT_SEC]


def test_role_settings_for_e():
    from app.nodes.evaluate.llm.settings import LLMSettings

    s = LLMSettings(project="p")
    assert s.role("validator").model == "gemini-3.8-flash" and s.role("validator").timeout_sec == 15
    assert s.role("validator").retries == 0
    assert s.role("coach").thinking_level == "LOW" and s.role("evaluator").thinking_level == "MEDIUM"


# ------------------------------------------------------------------ graph/ 연결 진입점


def test_evaluate_state_accepts_interview_state_and_validates_as_report_response():
    from app.nodes.evaluate import evaluate_state
    from app.schemas.api import ReportResponse
    from app.schemas.state import InterviewState

    inp = make_input()
    state = InterviewState(session_id=inp.session_id, resume_text="-", job_posting_text="-", job_description_text="-",
                           cover_letter_text="-", consent_at="2026-09-30T15:00:00+09:00", analysis=inp.analysis,
                           questions=inp.questions, answers=inp.answers)
    steps = []
    report = evaluate_state(state, FakeLLM(), on_step=lambda s, st: steps.append((s, st)))
    ReportResponse.model_validate(report)
    assert report == json.loads((MOCK_DIR / "report.json").read_text(encoding="utf-8"))
    assert ("compose", "DONE") in steps
