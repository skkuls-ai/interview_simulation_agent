"""꼬리질문 판단 LLM 에이전트: 가짜 LLM 으로 프롬프트, 안전장치, 실패 대응을 검증합니다."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.interview.agents import StubAnalysisAgents
from backend.interview.analysis_graph import build_analysis_graph
from backend.interview.llm_agents import HybridInterviewAgents, LLMFollowUpJudge, check_generated, element_question
from backend.interview.prompts.follow_up_judge import JudgeOutput
from backend.interview.state import QuestionThread, SessionConfig, Turn, VerificationPoint
from backend.llm.client import CallInfo, GeminiClient, LLMError
from backend.llm.settings import LLMSettings

from .conftest import BANK, default_answer, drive, full_consent, make_service


JUDGE_DEFAULTS = {
    "covered": [], "missing": [], "covered_intent_ids": [],
    "question_source": "none", "follow_up_id": "", "generated_question": "", "verification_point_id": "",
    "quality": "none", "inconsistency_note": "",
}


def full(out: dict) -> dict:
    """테스트에서는 필요한 칸만 쓰고 나머지는 기본값으로 채움 (실제 모델은 모든 칸을 채워야 함)."""
    return {**JUDGE_DEFAULTS, **out}


class FakeLLM:
    def __init__(self, outputs=None, error: Exception | None = None):
        self.outputs = list(outputs or [])
        self.error = error
        self.calls: list[dict] = []

    def generate_json(self, role, system, prompt, schema):
        self.calls.append({"role": role, "system": system, "prompt": prompt})
        if self.error:
            raise self.error
        out = self.outputs.pop(0) if self.outputs else {"action": "close", "quality": "SUFFICIENT", "rationale": "충분"}
        return schema.model_validate(full(out)), CallInfo(role=role, model="fake", latency_sec=0.01, attempts=1)


BP = build_analysis_graph(BANK, StubAnalysisAgents()).invoke({"config": SessionConfig(), "seed": 1})["blueprint"]


def thread(qid: str, *answers: str, follow_ups: list[str] | None = None) -> QuestionThread:
    q = BANK.get(qid)
    turns = [Turn(speaker="interviewer", kind="main", text=q.text)]
    for i, a in enumerate(answers):
        if i > 0:
            fid = (follow_ups or [])[i - 1] if follow_ups and i - 1 < len(follow_ups) else None
            text = next(f.text for f in q.follow_ups if f.id == fid) if fid else "구체적으로 말씀해 주세요."
            turns.append(Turn(speaker="interviewer", kind="follow_up" if fid else "generated_follow_up",
                              text=text, follow_up_id=fid))
        turns.append(Turn(speaker="candidate", kind="answer", text=a))
    return QuestionThread(thread_id=qid, stage="main", question_id=qid, category_code="performance",
                          competency_code=q.competency_code, turns=turns)


def judge_with(*outputs, **kw):
    llm = FakeLLM(outputs, **kw)
    return LLMFollowUpJudge(llm, BANK), llm


CFG = SessionConfig()


# ------------------------------------------------------------------ 프롬프트


def test_prompt_contains_what_the_judge_needs():
    j, llm = judge_with({"action": "close", "rationale": "ok"})
    th = thread("Q006", "네 있습니다.", "자격증 취득입니다.", follow_ups=["Q006-F1"])
    j.decide(BANK.get("Q006"), th, CFG, [], BP)
    p = llm.calls[0]["prompt"]
    assert llm.calls[0]["role"] == "follow_up_judge"
    assert "Q006-I1" in p and "스스로 명확한 목표를 설정하였다" in p       # 의도와 체크포인트
    assert '"condition": "성취했다면"' in p                                  # 조건부 후보
    assert "Q006-F1" not in p.split("## 원본 꼬리질문 후보")[1].split("## 진행 상태")[0]  # 쓴 후보 제외
    assert '"남은_꼬리질문": 2' in p
    assert p.rstrip().endswith("지원자: 자격증 취득입니다.")                  # 직전 답변이 마지막
    assert "끊임없이 무엇인가를 이루고자 하는 마음" in p                        # 역량 정의


def test_prompt_marks_shared_follow_ups_and_fallback():
    j, llm = judge_with({"action": "close", "rationale": "ok"}, {"action": "close", "rationale": "ok"})
    j.decide(BANK.get("Q023"), thread("Q023", "잘 모르겠습니다."), CFG, [], BP)
    assert '"shared": true' in llm.calls[0]["prompt"]
    j.decide(BANK.get("Q016"), thread("Q016", "그런 경험이 없습니다."), CFG, [], BP)
    assert "fallback_text" in llm.calls[1]["prompt"] and "사소한 경험이라도" in llm.calls[1]["prompt"]


# ------------------------------------------------------------------ 안전장치


def test_valid_original_follow_up_passes_through():
    j, _ = judge_with({"action": "ask_follow_up", "follow_up_id": "Q006-F2", "missing": ["result"],
                       "covered": ["situation"], "covered_intent_ids": ["Q006-I1", "X-9"], "rationale": "결과 확인"})
    d = j.decide(BANK.get("Q006"), thread("Q006", "자격증을 목표로 했습니다."), CFG, [], BP)
    assert d.action == "ask_follow_up" and d.follow_up_id == "Q006-F2" and d.decided_by == "llm"
    assert d.covered_intent_ids == ["Q006-I1"]  # 없는 의도 ID 제거


def test_unknown_or_used_follow_up_id_is_replaced():
    j, _ = judge_with({"action": "ask_follow_up", "follow_up_id": "Q006-F1", "rationale": "x"})
    th = thread("Q006", "네.", "이유는 성장입니다.", follow_ups=["Q006-F1"])
    d = j.decide(BANK.get("Q006"), th, CFG, [], BP)
    # 원본을 기계적으로 고르지 않고 공백을 묻는 중립 질문으로 대체
    assert d.follow_up_id is None and d.generated_question == element_question([], True) and "보정" in d.rationale


@pytest.mark.parametrize("bad", [
    "결혼은 하셨나요?", "부모님은 어떤 일을 하시나요?", "고향이 어디세요?", "나이가 어떻게 되시나요?",
    "성과역량 관점에서 본인은 어떻다고 생각하시나요?", "가" * 130,
])
def test_generated_question_guard_rejects(bad):
    assert check_generated(bad) is not None
    j, _ = judge_with({"action": "ask_follow_up", "generated_question": bad, "rationale": "x"})
    d = j.decide(BANK.get("Q006"), thread("Q006", "네 있습니다."), CFG, [], BP)
    assert d.generated_question == element_question([], True) and d.follow_up_id is None


def test_good_generated_question_kept():
    q = "말씀하신 이탈률 개선에서 본인이 직접 바꾼 것은 무엇이었나요?"
    assert check_generated(q) is None
    j, _ = judge_with({"action": "ask_follow_up", "generated_question": q, "missing": ["action"], "rationale": "x"})
    d = j.decide(BANK.get("Q006"), thread("Q006", "우리 팀이 이탈률을 낮췄습니다."), CFG, [], BP)
    assert d.generated_question == q and d.missing == ["action"]


def test_empty_question_fields_regression():
    """첫 실제 평가에서 나온 문제: ask 인데 질문 칸이 비어 있으면 맥락 무관한 첫 후보를 고르던 동작."""
    j, _ = judge_with(
        # Q023 (공유 꼬리질문): 이유를 묻겠다고 했지만 질문 칸이 빔
        {"action": "ask_follow_up", "question_source": "original", "missing": ["reason", "alternative"],
         "covered": ["judgment"], "rationale": "이유 확인"},
        # Q016: 대체 안내를 쓰겠다고 함
        {"action": "ask_follow_up", "question_source": "fallback_text", "rationale": "경험 없음"},
        # 검증 포인트를 지정했지만 질문이 비어 있음
        {"action": "ask_follow_up", "question_source": "generated", "verification_point_id": "V1",
         "missing": ["action"], "rationale": "규모 확인"},
    )
    d = j.decide(BANK.get("Q023"), thread("Q023", "비용 기준으로 분류하겠습니다."), CFG, [], BP)
    assert d.follow_up_id is None and d.generated_question == "그렇게 판단하신 이유는 무엇입니까?"
    d = j.decide(BANK.get("Q016"), thread("Q016", "그런 경험은 없습니다."), CFG, [], BP)
    assert d.generated_question == BANK.get("Q016").fallback_text and "보정" not in d.rationale
    p = VerificationPoint(id="V1", claim="대규모 채용", concern="규모 근거 부족", category_codes=["performance"])
    d = j.decide(BANK.get("Q006"), thread("Q006", "채용을 운영했습니다."), CFG, [p], BP)
    assert d.verification_point_id is None  # 대체 질문에는 검증 포인트 표시를 붙이지 않음


def test_judge_output_fields_are_all_required():
    schema = JudgeOutput.model_json_schema()
    assert set(schema["required"]) == set(schema["properties"])  # 선택 칸이 있으면 모델이 빼먹음
    assert list(schema["properties"])[-1] == "rationale"


def test_elements_filtered_by_question_type():
    j, _ = judge_with({"action": "close", "covered": ["reason", "action"], "missing": ["result", "alternative"],
                       "rationale": "x"})
    d = j.decide(BANK.get("Q023"), thread("Q023", "먼저 자료를 분류하겠습니다."), CFG, [], BP)  # 상황면접
    assert d.covered == ["reason"] and d.missing == ["alternative"]


def test_verification_point_must_exist():
    p = VerificationPoint(id="V1", claim="대규모 채용 경험", concern="규모 근거 부족", category_codes=["performance"])
    j, _ = judge_with(
        {"action": "ask_follow_up", "generated_question": "당시 채용 규모는 어느 정도였나요?", "verification_point_id": "V1", "rationale": "x"},
        {"action": "ask_follow_up", "generated_question": "당시 채용 규모는 어느 정도였나요?", "verification_point_id": "V9", "rationale": "x"},
    )
    assert j.decide(BANK.get("Q006"), thread("Q006", "채용을 운영했습니다."), CFG, [p], BP).verification_point_id == "V1"
    assert j.decide(BANK.get("Q006"), thread("Q006", "채용을 운영했습니다."), CFG, [p], BP).verification_point_id is None


def test_llm_failure_falls_back_without_stopping_interview():
    j, _ = judge_with(error=LLMError("timeout"))
    d1 = j.decide(BANK.get("Q006"), thread("Q006", "네."), CFG, [], BP)
    assert d1.decided_by == "fallback" and d1.action == "ask_follow_up" and d1.generated_question
    d2 = j.decide(BANK.get("Q006"), thread("Q006", "네.", "성장입니다.", follow_ups=["Q006-F1"]), CFG, [], BP)
    assert d2.action == "close" and d2.evidence_sufficient  # 한 번 물은 뒤엔 추가 문항을 유발하지 않게 종료


# ------------------------------------------------------------------ 그래프 연결


def test_hybrid_agents_drive_full_interview(tmp_path):
    """LLM 판단 결과가 그래프에 제대로 반영되는지: 첫 문항만 꼬리질문 2회, 나머지는 바로 종료."""
    class Script(FakeLLM):
        def generate_json(self, role, system, prompt, schema):
            self.calls.append({"role": role, "prompt": prompt})
            n = len(self.calls)
            if n <= 2:
                out = {"action": "ask_follow_up", "generated_question": "본인이 직접 하신 일은 무엇이었나요?",
                       "missing": ["action"], "rationale": "본인 행동 불분명"}
            else:
                out = {"action": "close", "quality": "SUFFICIENT", "rationale": "충분"}
            return schema.model_validate(full(out)), CallInfo(role=role, model="fake", latency_sec=0.01, attempts=1)

    llm = Script()
    s = make_service(tmp_path, interview_agents=HybridInterviewAgents(BANK, llm))
    sid = s.create_session(full_consent(documents=False))
    s.analyze(sid, seed=1)
    prompts, done = drive(s, sid)
    gen = [p for p in prompts if p.type == "await_answer" and p.kind == "generated_follow_up"]
    assert len(gen) == 2 and all(p.text == "본인이 직접 하신 일은 무엇이었나요?" for p in gen)
    decisions = [d for t in done["detail"]["threads"] for d in t["decisions"]]
    assert all(d["decided_by"] == "llm" for d in decisions)
    s.shutdown()


# ------------------------------------------------------------------ 클라이언트


def test_gemini_client_config_and_retry():
    from google.genai import types

    calls = []

    class Models:
        def generate_content(self, model, contents, config):
            calls.append((model, config))
            if len(calls) == 1:
                return SimpleNamespace(text="{not json", usage_metadata=None)
            return SimpleNamespace(text=json.dumps(full({"action": "close", "rationale": "ok"})),
                                   usage_metadata=SimpleNamespace(prompt_token_count=100, candidates_token_count=20))

    client = GeminiClient(LLMSettings(project="p"), client=SimpleNamespace(models=Models()))
    out, info = client.generate_json("follow_up_judge", "sys", "prompt", JudgeOutput)
    assert out.action == "close" and info.attempts == 2 and info.input_tokens == 100
    model, cfg = calls[0]
    assert model == "gemini-3.8-flash"
    assert cfg.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert cfg.response_mime_type == "application/json" and cfg.response_json_schema["title"] == "JudgeOutput"
    assert cfg.temperature is None  # 3.8 Flash 는 temperature 미지원
    assert "$ref" not in json.dumps(cfg.response_json_schema)  # 스키마를 펼쳐서 보냄
    assert "action" in cfg.response_json_schema["properties"]["missing"]["items"]["enum"]


def test_gemini_client_raises_after_retries():
    class Models:
        def generate_content(self, **kw):
            raise RuntimeError("429 quota")

    client = GeminiClient(LLMSettings(project="p"), client=SimpleNamespace(models=Models()))
    with pytest.raises(LLMError):
        client.generate_json("follow_up_judge", "s", "p", JudgeOutput)


def test_model_override_from_env(monkeypatch):
    # PC 의 .env 나 환경변수에 영향받지 않도록 관련 값을 비움
    import os
    for key in list(os.environ):
        if key == "GEMINI_MODEL" or key.startswith("INTERVIEW_MODEL_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setenv("INTERVIEW_MODEL_FOLLOW_UP_JUDGE", "gemini-3.7-flash")
    s = LLMSettings.from_env()
    assert s.project == "proj" and s.role("follow_up_judge").model == "gemini-3.7-flash"
    assert s.role("evaluator").model == "gemini-3.8-flash"

    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.7-flash")
    s = LLMSettings.from_env()
    assert s.role("evaluator").model == "gemini-3.7-flash"   # GEMINI_MODEL 이 기본 모델을 바꿈
    assert s.role("validator").model == "gemini-3.7-flash"   # 검증 역할은 원래 3.7
