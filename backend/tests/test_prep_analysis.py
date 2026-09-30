"""서류 분석(app/nodes/prep/analysis.py) 테스트. 가짜 LLM 이라 API 호출이 없습니다.

확인하는 것 (docs/08 T-203, T-204 포함)
- 채용공고·직무기술서를 따로 분석하고 RQ- 를 순서대로 발급하는지
- 원문에 없는 요구사항·주장은 버리고, 주장은 원문 글자로 저장하는지 (T-204)
- 연결·검증 포인트가 참조한 ID 가 실제로 있는지 검사하는지 (T-203)
- LLM 이 실패해도 대체값으로 계약 모양의 Analysis 가 나오는지
- run_analysis 가 화면 3의 단계 진행을 순서대로 알리는지
"""

from __future__ import annotations

import json
from pathlib import Path

from app.nodes.prep import analysis as A
from app.nodes.prep import analysis_prompts as P
from app.schemas.state import Analysis, Claim, Requirement

DEMO = Path(__file__).parent / "fixtures" / "prep_demo"
DOCS = json.loads((DEMO / "sample_inputs.json").read_text(encoding="utf-8"))
RESUME, POSTING = DOCS["resume_text"], DOCS["job_posting_text"]
DESCRIPTION, COVER = DOCS["job_description_text"], DOCS["cover_letter_text"]


class FakeLLM:
    """출력 모델 종류별로 답을 고릅니다. 요구사항은 프롬프트의 문서 이름([채용공고]/[직무기술서])으로 구분."""

    def __init__(self, outputs: dict | None = None, error: Exception | None = None):
        self.outputs = outputs or {}
        self.error = error
        self.calls: list[dict] = []

    def generate_json(self, role, system, prompt, schema):
        self.calls.append({"role": role, "prompt": prompt, "schema": schema})
        if self.error:
            raise self.error
        key = schema
        if schema is P.RequirementsOutput:
            key = (schema, "job_posting" if prompt.startswith("[채용공고]") else "job_description")
        return schema.model_validate(self.outputs[key]), None


def req(text, quote, kind="SKILL"):
    return {"text": text, "kind": kind, "source_quote": quote}


def claim(doc, text, types, exp="레시피 RAG 챗봇"):
    return {"source_doc": doc, "experience": exp, "text": text, "types": types}


def report():
    return A.AnalysisReport(analysis=Analysis(requirements=[], claims=[], checkpoints=[], links=[]))


POSTING_OUT = {"requirements": [
    req("정량 평가·모니터링 경험", "LLM 응답 품질을 정량적으로 평가하고 모니터링한 경험"),
    req("담당 업무", "담당 업무", "DUTY"),                         # 섹션 제목 (8자 미만 → 버림)
    req("Kubernetes 운영", "Kubernetes 클러스터 운영 경험"),        # 원문에 없음 (환각)
    req("근거 기반 문제 해결", "문제를 스스로 정의하고 근거를 바탕으로 해결하는 사람", "TALENT"),
]}
DESCRIPTION_OUT = {"requirements": [
    req("Docker 배포·운영", "Docker 기반 서비스 배포와 운영"),
    req("로그·품질 모니터링", "FastAPI 서비스 API 개발, 로그 수집과 응답 품질 모니터링", "DUTY"),
]}
CLAIMS_OUT = {"claims": [
    claim("cover_letter", "검색 정확도를 20% 개선했습니다", ["METRIC"]),
    claim("resume", "전처리 규칙과 임베딩 문서 구성을 바꿔 검색 정확도 20% 개선", ["METRIC"]),
    claim("resume", "만개의레시피 데이터 1,000개를 크롤링·전처리해", ["METRIC"]),
    claim("cover_letter", "약 5,000개의 레시피 데이터를 수집해", ["METRIC"]),
    claim("resume", "사용자 이탈을 절반 이하로 줄였습니다", ["METRIC", "PROBLEM"], "ProofLetter"),  # 서류 구분 틀림 → 정정
    claim("cover_letter", "검색 정확도를 50% 개선했습니다", ["METRIC"]),                         # 숫자 바꿈 → 버림
    claim("cover_letter", "검색 정확도를 20% 개선했습니다.", ["METRIC"]),                        # 같은 위치 중복
]}


# ================================================================ 요구사항


def test_requirements_are_per_document_with_sequential_ids():
    llm = FakeLLM({(P.RequirementsOutput, "job_posting"): POSTING_OUT, (P.RequirementsOutput, "job_description"): DESCRIPTION_OUT})
    rep = report()
    reqs = A.read_postings(llm, POSTING, DESCRIPTION, rep)

    assert [(r.requirement_id, r.source_doc, r.kind) for r in reqs] == [
        ("RQ-001", "job_posting", "SKILL"),
        ("RQ-002", "job_posting", "TALENT"),
        ("RQ-003", "job_description", "SKILL"),
        ("RQ-004", "job_description", "DUTY"),
    ]
    issues = " ".join(rep.issues["read_posting:job_posting"])
    assert "담당 업무" in issues and "Kubernetes" in issues
    assert len([c for c in llm.calls if c["schema"] is P.RequirementsOutput]) == 2  # 문서별로 따로 호출


def test_requirements_fallback_when_llm_fails():
    rep = report()
    reqs = A.read_postings(FakeLLM(error=RuntimeError("quota")), POSTING, DESCRIPTION, rep)
    assert reqs and set(rep.fallbacks) == {"read_posting:job_posting", "read_posting:job_description"}
    texts = [r.text for r in reqs]
    assert "LLM 응답 품질을 정량적으로 평가하고 모니터링한 경험" in texts
    assert all(len(t) >= 8 for t in texts)  # 섹션 제목은 들어가지 않음
    kinds = {r.text: r.kind for r in reqs}
    assert kinds["문제를 스스로 정의하고 근거를 바탕으로 해결하는 사람"] == "TALENT"
    assert kinds["LangChain·LangGraph 기반 멀티 에이전트 워크플로우 설계와 구현"] == "DUTY"


def test_short_listed_requirement_items_are_kept_but_headings_are_not():
    jd = "필요 지식: Python, 벡터 데이터베이스, Git 협업\n필요 역량: 문제 정의 능력, 우선순위 판단\n담당 업무\n- Docker\n"
    out = P.RequirementsOutput.model_validate({"requirements": [
        req("Python", "Python"),
        req("Git 협업", "Git 협업"),
        req("우선순위 판단", "우선순위 판단", "TALENT"),
        req("Docker", "Docker"),                 # 글머리표 항목은 줄 전체여도 인정
        req("담당 업무", "담당 업무", "DUTY"),     # 글머리표 없는 제목 줄 → 버림
        req("필요 지식", "필요 지식"),             # 뒤에 ":" 가 오는 줄머리 → 버림
        req("Kotlin", "Kotlin"),                 # 원문에 없음 → 버림
    ]})
    issues: list[str] = []
    items = A.sanitize_requirements(out, jd, issues)
    assert [q for _, _, q in items] == ["Python", "Git 협업", "우선순위 판단", "Docker"]
    assert len(issues) == 3


# ================================================================ 주장


def test_claims_are_verbatim_deduplicated_and_source_fixed():
    rep = report()
    claims, experiences = A.read_resume(FakeLLM({P.ClaimsOutput: CLAIMS_OUT}), RESUME, COVER, rep)

    llm_claims = claims[:5]  # 뒤의 2개는 "기술 스택" 글머리표 줄 (아래 기술 목록 테스트)
    assert [c.claim_id for c in llm_claims] == ["CL-001", "CL-002", "CL-003", "CL-004", "CL-005"]
    assert [c.source_doc for c in llm_claims] == ["cover_letter", "resume", "resume", "cover_letter", "cover_letter"]
    for c in claims:  # T-204: Claim.text 는 서류 원문에 그대로 있음
        assert c.text in (RESUME if c.source_doc == "resume" else COVER)
    issues = " ".join(rep.issues["read_resume"])
    assert "50%" in issues and "서류 구분 정정" in issues and "중복" in issues
    assert rep.experience_count == 2  # 레시피 RAG 챗봇, ProofLetter
    assert experiences["CL-005"] == "ProofLetter"


def test_skill_list_lines_become_link_only_claims():
    # 김하늘 이력서: "기술 스택" 제목 아래 글머리표 줄 2개
    rep = report()
    claims, _ = A.read_resume(FakeLLM({P.ClaimsOutput: CLAIMS_OUT}), RESUME, COVER, rep)
    skills = [c for c in claims if c.claim_id in rep.skill_claim_ids]
    assert [(c.claim_id, c.text, c.types) for c in skills] == [
        ("CL-006", "Python, pandas, PostgreSQL, FastAPI, React", ["TECH"]),
        ("CL-007", "Gemini API, LangChain, LangGraph, ChromaDB, NetworkX", ["TECH"]),
    ]
    assert rep.experience_count == 2                        # 경험 수에 넣지 않음
    rep.analysis = Analysis(claims=claims)
    assert rep.details["read_resume"].endswith("확인할 주장 5개")  # 확인할 주장에도 넣지 않음


def test_inline_skill_line_is_kept_whole_and_not_duplicated():
    resume = "기술: Python, FastAPI, LangGraph 학습 중, Git\n- 검색 정확도를 20% 개선했습니다."
    assert [t for _, t, *_ in A.skill_list_claims(resume, [], [])] == ["기술: Python, FastAPI, LangGraph 학습 중, Git"]
    taken = [("resume", "기술: Python, FastAPI, LangGraph 학습 중, Git", ["TECH"], "기타")]
    assert A.skill_list_claims(resume, taken, []) == []     # LLM 이 이미 뽑았으면 다시 넣지 않음


def test_skill_claims_are_marked_for_link_and_excluded_from_checkpoints():
    llm = FakeLLM({
        (P.RequirementsOutput, "job_posting"): POSTING_OUT,
        (P.RequirementsOutput, "job_description"): DESCRIPTION_OUT,
        P.ClaimsOutput: CLAIMS_OUT,
        P.LinksOutput: {"links": [{"requirement_id": "RQ-001", "claim_ids": ["CL-006"]}]},
        P.CheckpointsOutput: {"checkpoints": [cp(["CL-006"], "기술 목록만 참조", "high"), cp(["CL-001"], "측정 기준", "high")]},
    })
    rep = A.run_analysis(llm, RESUME, POSTING, DESCRIPTION, COVER)
    link_prompt = next(c["prompt"] for c in llm.calls if c["schema"] is P.LinksOutput)
    cp_prompt = next(c["prompt"] for c in llm.calls if c["schema"] is P.CheckpointsOutput)
    assert "(TECH) [기술 목록] Python, pandas" in link_prompt
    assert "CL-006" not in cp_prompt
    assert rep.analysis.links[0].claim_ids == ["CL-006"]                  # 연결 근거로는 인정
    assert [c.title for c in rep.analysis.checkpoints] == ["측정 기준"]    # 검증 포인트에서는 제외


def test_claims_fallback_when_llm_fails():
    rep = report()
    claims, _ = A.read_resume(FakeLLM(error=RuntimeError("timeout")), RESUME, COVER, rep)
    assert claims and "read_resume" in rep.fallbacks
    texts = " ".join(c.text for c in claims)
    assert "20%" in texts and "1,000개" in texts and "주도" in texts


# ================================================================ 연결


REQS = [Requirement(requirement_id=f"RQ-00{i}", text=t, source_doc="job_posting", kind="SKILL")
        for i, t in enumerate(["RAG 또는 벡터 DB 활용 경험", "LLM 응답 품질 정량 평가·모니터링", "Docker 배포"], 1)]
CLAIMS = [
    Claim(claim_id="CL-001", source_doc="cover_letter", text="검색 정확도를 20% 개선했습니다", types=["METRIC"]),
    Claim(claim_id="CL-002", source_doc="cover_letter", text="프로젝트를 주도했습니다", types=["ROLE"]),
]


def test_links_drop_unknown_ids_and_fill_missing_requirements():
    rep = report()
    out = {"links": [
        {"requirement_id": "RQ-001", "claim_ids": ["CL-001", "CL-999", "CL-001"]},  # 없는 ID, 중복
        {"requirement_id": "RQ-404", "claim_ids": ["CL-002"]},                     # 없는 요구사항
    ]}
    links = A.link(FakeLLM({P.LinksOutput: out}), REQS, CLAIMS, rep)

    assert [(l.requirement_id, l.claim_ids) for l in links] == [("RQ-001", ["CL-001"]), ("RQ-002", []), ("RQ-003", [])]
    issues = " ".join(rep.issues["link"])
    assert "CL-999" in issues and "RQ-404" in issues and "근거 없음" in issues


# ================================================================ 검증 포인트


def cp(ids, title, priority="medium"):
    return {"claim_ids": ids, "title": title, "what_to_verify": f"{title}을 확인합니다.", "priority": priority}


def test_checkpoints_validate_ids_sort_by_priority_and_issue_ids():
    rep = report()
    out = {"checkpoints": [
        cp(["CL-002"], "주도한 역할", "medium"),
        cp(["CL-001"], "검색 품질 측정 기준", "high"),
        cp(["CL-777"], "없는 주장만 참조", "high"),        # 근거 주장이 모두 없음 → 제외
        cp(["CL-001", "CL-404"], "같은 묶음 중복", "low"),  # CL-404 제거 후 CL-001 묶음과 중복 → 제외
    ]}
    cps = A.checkpoints(FakeLLM({P.CheckpointsOutput: out}), REQS, CLAIMS, {}, rep)

    assert [(c.checkpoint_id, c.title, c.claim_ids) for c in cps] == [
        ("CP-001", "검색 품질 측정 기준", ["CL-001"]),
        ("CP-002", "주도한 역할", ["CL-002"]),
    ]
    issues = " ".join(rep.issues["checkpoints"])
    assert "CL-777" in issues and "CL-404" in issues


def test_checkpoints_fallback_by_claim_type():
    rep = report()
    cps = A.checkpoints(FakeLLM(error=RuntimeError("down")), REQS, CLAIMS, {}, rep)
    assert [c.title for c in cps] == ["수치 성과의 측정 기준", "본인 역할의 구체 내용"]
    assert "checkpoints" in rep.fallbacks


# ================================================================ 전체


def test_run_analysis_reports_steps_in_order_with_details():
    llm = FakeLLM({
        (P.RequirementsOutput, "job_posting"): POSTING_OUT,
        (P.RequirementsOutput, "job_description"): DESCRIPTION_OUT,
        P.ClaimsOutput: CLAIMS_OUT,
        P.LinksOutput: {"links": [{"requirement_id": "RQ-001", "claim_ids": ["CL-001"]}]},
        P.CheckpointsOutput: {"checkpoints": [cp(["CL-001", "CL-002"], "검색 품질 측정 기준", "high")]},
    })
    events = []
    rep = A.run_analysis(llm, RESUME, POSTING, DESCRIPTION, COVER, on_step=lambda *e: events.append(e))

    done = [(s, d) for s, state, d in events if state == "DONE"]
    assert done == [
        ("read_posting", "요구사항 4개 확인"),
        ("read_resume", "경험 2개, 확인할 주장 5개"),
        ("link", None),
        ("checkpoints", None),
    ]
    a = rep.analysis
    assert len(a.links) == len(a.requirements)  # 요구사항마다 연결 결과 하나
    assert a.checkpoints[0].claim_ids == ["CL-001", "CL-002"]
    Analysis.model_validate(a.model_dump())  # 계약 모양 그대로


def test_run_analysis_without_llm_still_returns_contract_shape():
    rep = A.run_analysis(FakeLLM(error=RuntimeError("no provider")), RESUME, POSTING, DESCRIPTION, COVER)
    a = rep.analysis
    assert a.requirements and a.claims and a.checkpoints and len(a.links) == len(a.requirements)
    ids = {c.claim_id for c in a.claims}
    assert all(set(l.claim_ids) <= ids for l in a.links)          # T-203: 참조 ID 가 실제로 있음
    assert all(set(c.claim_ids) <= ids for c in a.checkpoints)
    assert len(set(rep.fallbacks)) == 5
