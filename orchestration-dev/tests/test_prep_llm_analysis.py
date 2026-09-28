"""분석 에이전트 LLM 구현 테스트 (가짜 LLM, API 호출 없음).

확인하는 것
- 원문에 없는 요구사항, 경험, 주장 구절은 버리고 원문 글자로 저장하는지
- 없는 역량 코드를 지우고 ID 를 코드가 붙이는지
- LLM 실패, 유효 항목 없음이면 스텁으로 대체하는지
- 분석 그래프 전체가 LLM 구현으로 끝까지 도는지
"""

from __future__ import annotations

from pathlib import Path

from backend.interview.agents import StubAnalysisAgents
from backend.interview.analysis_graph import build_analysis_graph
from backend.interview.llm_analysis_agents import LLMAnalysisAgents
from backend.interview.prompts import analysis as P
from backend.interview.state import SessionConfig
from backend.llm.client import CallInfo, LLMError
from tests.conftest import BANK

DEMO = Path(__file__).parents[1] / "data" / "demo"
JD = (DEMO / "jd.txt").read_text(encoding="utf-8")
RESUME = (DEMO / "resume.txt").read_text(encoding="utf-8")
COVER = (DEMO / "cover_letter.txt").read_text(encoding="utf-8")


class FakeLLM:
    """요청한 출력 모델 종류별로 정해진 답을 돌려줍니다 (병렬 노드의 호출 순서와 무관)."""

    def __init__(self, outputs: dict | None = None, error: Exception | None = None):
        self.outputs = outputs or {}
        self.error = error
        self.calls: list[dict] = []

    def generate_json(self, role, system, prompt, schema):
        self.calls.append({"role": role, "system": system, "prompt": prompt, "schema": schema})
        if self.error:
            raise self.error
        return schema.model_validate(self.outputs[schema]), CallInfo(role=role, model="fake", latency_sec=0.01, attempts=1)


def req(text, quote, importance="must", kind="skill", codes=()):
    return {"text": text, "kind": kind, "importance": importance, "competency_codes": list(codes), "source_quote": quote}


def jd_output(requirements, company="브라이트런", role="AI Agent·LLM 애플리케이션 엔지니어 (신입)"):
    return {"company_name": company, "role_title": role, "mission_or_values": ["근거 기반 문제 해결"],
            "business_summary": "사내 문서 기반 업무 자동화 AI Agent", "requirements": requirements}


def exp(source, title, quote, claims=(), codes=()):
    return {"source": source, "title": title, "organization": None, "period": "2026.09", "summary": f"{title} 요약",
            "claimed_results": list(claims), "competency_codes": list(codes), "source_quote": quote}


def agents(outputs=None, error=None):
    llm = FakeLLM(outputs, error)
    return LLMAnalysisAgents(llm, BANK), llm


# ================================================================ JD 분석


def test_jd_keeps_only_requirements_found_in_posting():
    a, _ = agents({P.JDAnalysisOutput: jd_output([
        req("정량 평가·모니터링 경험", "- LLM 응답 품질을 정량적으로 평가하고 모니터링한 경험", codes=["performance_management", "bogus"]),
        req("Kubernetes 운영 경험", "Kubernetes 클러스터 운영 경험"),  # 공고에 없는 요구사항 (환각)
        req("담당 업무", "담당 업무", kind="duty"),                     # 섹션 제목: 8자 미만이라 인용으로 인정 안 됨
        req("Docker 배포 경험", "Docker 등을 이용한 서비스 배포 경험", importance="preferred"),
    ])})
    company, reqs = a.analyze_jd(JD)

    assert [r.id for r in reqs] == ["R1", "R2"]
    assert [r.text for r in reqs] == ["정량 평가·모니터링 경험", "Docker 배포 경험"]
    assert reqs[0].competency_codes == ["performance_management"]
    assert reqs[1].importance == "preferred"
    assert company.company_name == "브라이트런"
    issues = " ".join(a.last_issues["analyze_jd"])
    assert "Kubernetes" in issues and "bogus" in issues and "담당 업무" in issues


def test_jd_company_name_not_in_posting_is_dropped():
    a, _ = agents({P.JDAnalysisOutput: jd_output(
        [req("Python 개발 경험", "Python 기반 프로젝트 개발 경험")], company="넥스트웨이브")})
    company, _ = a.analyze_jd(JD)
    assert company.company_name is None
    assert company.role_title is not None


def test_jd_prompt_contains_competency_codes_and_posting():
    a, llm = agents({P.JDAnalysisOutput: jd_output([req("Python 개발 경험", "Python 기반 프로젝트 개발 경험")])})
    a.analyze_jd(JD)
    prompt = llm.calls[0]["prompt"]
    assert "problem_solving" in prompt and "collaboration" in prompt
    assert "LLM 응답 품질을 정량적으로 평가하고 모니터링한 경험" in prompt
    assert llm.calls[0]["role"] == "analysis"


def test_jd_llm_error_falls_back_to_stub():
    a, _ = agents(error=LLMError("timeout"))
    assert a.analyze_jd(JD) == StubAnalysisAgents().analyze_jd(JD)
    assert "스텁" in a.last_issues["analyze_jd"][-1]


def test_jd_without_any_valid_requirement_falls_back_to_stub():
    a, _ = agents({P.JDAnalysisOutput: jd_output([req("지어낸 요구", "공고 어디에도 없는 요구 문장입니다")])})
    assert a.analyze_jd(JD) == StubAnalysisAgents().analyze_jd(JD)


# ================================================================ 경험 분석


def test_experiences_keep_documents_separate_and_quotes_verbatim():
    a, _ = agents({P.ExperienceAnalysisOutput: {"experiences": [
        exp("resume", "레시피 RAG 챗봇", "레시피 RAG 챗봇 (2026.09, 4인 팀)",
            claims=["만개의레시피 데이터 1,000개를 크롤링·전처리해"], codes=["information_management"]),
        exp("cover_letter", "레시피 RAG 챗봇", "첫 프로젝트인 레시피 RAG 챗봇에서는",
            claims=["약 5,000개의 레시피 데이터를 수집해", "검색 정확도를 30% 개선했습니다"]),
    ]}})
    exps = a.analyze_experiences(RESUME, COVER)

    assert [(e.id, e.source) for e in exps] == [("E1", "resume"), ("E2", "cover_letter")]
    # 두 서류의 숫자가 다르면 합치지 않고 각각 남깁니다 (서류 간 불일치를 다음 단계에서 찾을 수 있도록)
    assert exps[0].claimed_results == ["만개의레시피 데이터 1,000개를 크롤링·전처리해"]
    assert exps[1].claimed_results == ["약 5,000개의 레시피 데이터를 수집해", "검색 정확도를 30% 개선했습니다"]


def test_experiences_drop_changed_or_invented_claims():
    a, _ = agents({P.ExperienceAnalysisOutput: {"experiences": [
        exp("cover_letter", "ProofLetter", "ProofLetter 프로젝트에서 저는 3명의 팀원과 함께",
            claims=["사용자 이탈을 70% 줄였습니다",          # 숫자를 바꿈
                    "사용자 이탈을 절반 이하로 줄였습니다",    # 원문 그대로
                    "사용자 이탈을 절반 이하로 줄였습니다."],  # 같은 구절 중복
            codes=["collaboration", "leadership"]),         # leadership 은 영역 코드라 역량 코드가 아님
    ]}})
    [e] = a.analyze_experiences(RESUME, COVER)
    assert e.claimed_results == ["사용자 이탈을 절반 이하로 줄였습니다"]
    assert e.competency_codes == ["collaboration"]
    issues = " ".join(a.last_issues["analyze_experiences"])
    assert "70%" in issues and "leadership" in issues


def test_experiences_fix_wrong_source_and_drop_invented_experience():
    a, _ = agents({P.ExperienceAnalysisOutput: {"experiences": [
        # 자소서 문장인데 resume 로 잘못 표시 → cover_letter 로 정정
        exp("resume", "ProofLetter", "Pydantic 스키마로 에이전트 간 데이터 형식을 먼저 합의하자고 제안했고"),
        # 어느 서류에도 없는 경험 → 제외
        exp("resume", "사내 해커톤 대상", "사내 해커톤에서 대상을 수상했습니다"),
    ]}})
    [e] = a.analyze_experiences(RESUME, COVER)
    assert e.source == "cover_letter"
    assert "해커톤" in " ".join(a.last_issues["analyze_experiences"])


def test_experiences_without_documents_do_not_call_llm():
    a, llm = agents()
    assert a.analyze_experiences(None, "  ") == []
    assert llm.calls == []


def test_experiences_llm_error_falls_back_to_stub():
    a, _ = agents(error=LLMError("quota"))
    assert a.analyze_experiences(RESUME, COVER) == StubAnalysisAgents().analyze_experiences(RESUME, COVER)


# ================================================================ 그래프 전체


def test_analysis_graph_runs_end_to_end_with_llm_agents():
    a, llm = agents({
        P.JDAnalysisOutput: jd_output([
            req("멀티 에이전트 설계·구현", "LangChain·LangGraph 기반 멀티 에이전트 워크플로우 설계와 구현",
                kind="duty", codes=["expertise"]),
            req("팀 협업 경험", "팀 프로젝트에서 역할을 나누고 협업한 경험", kind="experience", codes=["collaboration"]),
        ]),
        P.ExperienceAnalysisOutput: {"experiences": [
            exp("cover_letter", "ProofLetter", "ProofLetter 프로젝트에서 저는 3명의 팀원과 함께",
                claims=["프로젝트를 주도했습니다"], codes=["collaboration"]),
        ]},
    })
    bp = build_analysis_graph(BANK, a).invoke({
        "config": SessionConfig(), "seed": 1, "jd_text": JD, "resume_text": RESUME, "cover_letter_text": COVER,
    })["blueprint"]

    assert [r.text for r in bp.requirements] == ["멀티 에이전트 설계·구현", "팀 협업 경험"]
    assert bp.experiences[0].claimed_results == ["프로젝트를 주도했습니다"]
    assert bp.company.company_name == "브라이트런"
    assert len(llm.calls) == 2  # 아직 LLM 으로 바꾼 메서드는 두 개뿐
