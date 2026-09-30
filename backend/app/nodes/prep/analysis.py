"""서류 분석 (담당 A, docs/03 F-003 · docs/05 준비 파이프라인 1~4단계).

    read_posting  채용공고·직무기술서 → Requirement   (LLM, 문서별로 따로 호출)
    read_resume   이력서·자소서      → Claim         (LLM)
    (코드)        원문 포함 검사, RQ-/CL-/CP- 발급
    link          Requirement ↔ Claim → RequirementLink (LLM, 코드가 ID 존재 검사)
    checkpoints   Claim → Checkpoint               (LLM, 코드가 ID 존재 검사)

C 는 단계별 함수를 그래프 노드로 쓰거나, run_analysis() 를 통째로 부르면 됩니다.
on_step(step_id, state, detail) 콜백으로 화면 3의 단계 진행(steps)을 기록할 수 있습니다.

LLM 출력은 그대로 믿지 않습니다 (docs/05 책임 경계).
- 인용·주장 문장은 원문에 있을 때만 남기고, 원문 글자 그대로 저장합니다.
- ID 는 코드가 발급합니다. LLM 이 참조한 ID 는 실제로 있는지 검사하고 없으면 버립니다.
- 호출이 실패하거나(클라이언트 재시도 포함) 남은 항목이 없으면 규칙 기반 대체값을 넣습니다.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Protocol, TypeVar

from pydantic import BaseModel

from . import analysis_prompts as P
from app.schemas.state import Analysis, Checkpoint, Claim, Question, Requirement, RequirementLink
from app.validators.quotes import QuoteMatch, compact_len, find_quote, normalize
from .competency_questions import build_competency_question_node
from .technical_questions import build_technical_question_node

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
ROLE = "analysis"
MAX_REQUIREMENTS_PER_DOC = 20
MAX_CLAIMS = 30
MAX_CHECKPOINTS = 8
MIN_REQUIREMENT_QUOTE_CHARS = 2  # "Python", "Git 협업" 같은 나열 항목 (주장 인용은 8자 규칙 그대로)
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

POSTING_DOCS = {"job_posting": "채용공고", "job_description": "직무기술서"}
STEP_LABELS = {
    "read_posting": "채용공고 읽는 중",
    "read_resume": "이력서·자소서 읽는 중",
    "link": "공고와 경험 연결 중",
    "checkpoints": "검증 포인트 찾는 중",
    "competency_questions": "직무 적합 인성 질문 고르는 중",
    "technical_questions": "기술 면접 질문 만드는 중",
}


class JsonLLM(Protocol):
    """LLM 클라이언트 인터페이스. 제공사가 정해지면 C 의 클라이언트가 이 모양을 따르면 됩니다."""

    def generate_json(self, role: str, system: str, prompt: str, schema: type[T]) -> tuple[T, object]: ...


StepCallback = Callable[[str, str, str | None], None]


@dataclass
class AnalysisReport:
    """분석 결과와 부가 정보. analysis 만 State 에 들어가고, 나머지는 화면 문구와 디버깅용입니다."""

    analysis: Analysis
    competency_question_status: str = "insufficient_analysis"
    competency_questions: list[Question] = field(default_factory=list)
    competency_question_reasons: list[str] = field(default_factory=list)
    technical_question_status: str = "insufficient_analysis"
    technical_questions: list[Question] = field(default_factory=list)
    experience_count: int = 0
    requirement_quotes: dict[str, str] = field(default_factory=dict)  # RQ- → 원문 구절 (계약 밖, 채점·연결 표시용)
    issues: dict[str, list[str]] = field(default_factory=dict)  # 단계별 안전장치 기록
    fallbacks: list[str] = field(default_factory=list)  # 대체값을 쓴 단계
    skill_claim_ids: set[str] = field(default_factory=set)  # 기술 목록 줄 (연결 근거로만, 검증 포인트 제외)

    @property
    def details(self) -> dict[str, str]:
        a = self.analysis
        return {
            "read_posting": f"요구사항 {len(a.requirements)}개 확인",
            "read_resume": f"경험 {self.experience_count}개, 확인할 주장 {len(a.claims) - len(self.skill_claim_ids)}개",
        }


# ================================================================ 1. 채용공고·직무기술서 → 요구사항


def read_postings(llm: JsonLLM, job_posting_text: str, job_description_text: str, report: AnalysisReport) -> list[Requirement]:
    """두 문서를 따로 분석해(한 번에 넣으면 항목이 많아 잘림) 채용공고 → 직무기술서 순으로 RQ- 를 붙입니다."""
    texts = {"job_posting": job_posting_text, "job_description": job_description_text}
    with ThreadPoolExecutor(2) as pool:
        futures = {doc: pool.submit(_requirements_for_doc, llm, doc, texts[doc], report) for doc in POSTING_DOCS}
        drafts = {doc: f.result() for doc, f in futures.items()}

    reqs: list[Requirement] = []
    for doc in POSTING_DOCS:
        for text, kind, quote in drafts[doc]:
            rid = f"RQ-{len(reqs) + 1:03d}"
            reqs.append(Requirement(requirement_id=rid, text=text, source_doc=doc, kind=kind))
            report.requirement_quotes[rid] = quote
    return reqs


def _requirements_for_doc(llm: JsonLLM, doc: str, text: str, report: AnalysisReport) -> list[tuple[str, str, str]]:
    step = f"read_posting:{doc}"
    issues = report.issues.setdefault(step, [])
    try:
        out, _ = llm.generate_json(ROLE, P.REQUIREMENTS_SYSTEM, P.build_requirements_prompt(POSTING_DOCS[doc], text), P.RequirementsOutput)
        items = sanitize_requirements(out, text, issues)
    except Exception as e:  # 클라이언트가 재시도한 뒤에도 실패
        issues.append(f"LLM 실패: {e}")
        items = []
    if not items:
        report.fallbacks.append(step)
        issues.append("유효한 요구사항 없음 → 규칙 기반 대체값 사용")
        items = fallback_requirements(text)
    return items


def sanitize_requirements(out: P.RequirementsOutput, text: str, issues: list[str]) -> list[tuple[str, str, str]]:
    """(요약, 종류, 원문 구절) 목록."""
    items: list[tuple[str, str, str]] = []
    seen: set[tuple[int, int, str]] = set()
    for d in out.requirements:
        m = find_requirement_quote(d.source_quote, text)
        if m is None:
            issues.append(f"원문에 없는 인용이라 제외: {d.text!r} / {d.source_quote!r}")
            continue
        summary = (d.text or "").strip() or m.text
        key = (m.start, m.end, normalize(summary))
        if key in seen:
            issues.append(f"중복 제외: {summary!r}")
            continue
        seen.add(key)
        items.append((summary[:80], d.kind, m.text))
        if len(items) >= MAX_REQUIREMENTS_PER_DOC:
            issues.append(f"항목이 많아 앞의 {MAX_REQUIREMENTS_PER_DOC}개만 사용")
            break
    return items


_BULLET = re.compile(r"^(?:[-•·]|\d+\.)")


def find_requirement_quote(quote: str | None, text: str) -> QuoteMatch | None:
    """요구사항 인용 찾기. 8자 미만이어도 "필요 지식: Python, Git 협업" 같은 줄의 나열 항목이면 인정합니다.

    짧은 인용은 섹션 제목을 요구사항으로 착각한 경우가 많아서 두 가지는 버립니다.
    - 줄 전체가 그 인용뿐이고 글머리표가 없는 줄 (예: "담당 업무")
    - 바로 뒤에 ":" 가 오는 줄머리 (예: "필요 지식:")
    """
    if m := find_quote(quote, text):
        return m
    m = find_quote(quote, text, min_chars=MIN_REQUIREMENT_QUOTE_CHARS)
    if m is None:
        return None
    start = text.rfind("\n", 0, m.start) + 1
    end = text.find("\n", m.end)
    line = text[start:len(text) if end < 0 else end].strip()
    if compact_len(line) == compact_len(m.text) and not _BULLET.match(line):
        return None
    if text[m.end:m.end + 3].lstrip(" )")[:1] in (":", "："):
        return None
    return m


_TALENT_HINT = re.compile(r"인재상|태도|사람$|가치")
_DUTY_HINT = re.compile(r"담당|주요 업무|업무")


def fallback_requirements(text: str) -> list[tuple[str, str, str]]:
    """LLM 없이: 글머리표·번호가 붙은 줄을 요구사항으로, 직전 섹션 제목으로 종류를 추정합니다."""
    items: list[tuple[str, str, str]] = []
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(?:[-•·]|\d+\.)\s*(.+)$", line)
        if not m:
            section = line  # 글머리표 없는 줄은 섹션 제목으로 봄
            continue
        body = m.group(1).strip()
        if len(body) < 8:
            continue
        kind = "TALENT" if _TALENT_HINT.search(section) else "DUTY" if _DUTY_HINT.search(section) else "SKILL"
        items.append((body[:80], kind, body))
    return items[:MAX_REQUIREMENTS_PER_DOC]


# ================================================================ 2. 이력서·자소서 → 주장


def read_resume(llm: JsonLLM, resume_text: str, cover_letter_text: str, report: AnalysisReport) -> tuple[list[Claim], dict[str, str]]:
    """주장과, 주장 ID → 경험 이름 (검증 포인트 프롬프트와 "경험 n개" 문구에만 씀)."""
    docs = {"resume": resume_text, "cover_letter": cover_letter_text}
    issues = report.issues.setdefault("read_resume", [])
    try:
        out, _ = llm.generate_json(ROLE, P.CLAIMS_SYSTEM, P.build_claims_prompt(resume_text, cover_letter_text), P.ClaimsOutput)
        drafts = sanitize_claims(out, docs, issues)
    except Exception as e:
        issues.append(f"LLM 실패: {e}")
        drafts = []
    if not drafts:
        report.fallbacks.append("read_resume")
        issues.append("유효한 주장 없음 → 규칙 기반 대체값 사용")
        drafts = fallback_claims(docs)
    skills = skill_list_claims(resume_text, drafts, issues)

    claims, experiences = [], {}
    for source_doc, text, types, experience in drafts + skills:
        cid = f"CL-{len(claims) + 1:03d}"
        claims.append(Claim(claim_id=cid, source_doc=source_doc, text=text, types=types))
        experiences[cid] = experience
    report.skill_claim_ids = {c.claim_id for c in claims[len(drafts):]}
    report.experience_count = len({normalize(e).lower() for e in experiences.values() if e and e != "기타"})
    return claims, experiences


def sanitize_claims(out: P.ClaimsOutput, docs: dict[str, str], issues: list[str]) -> list[tuple[str, str, list[str], str]]:
    other = {"resume": "cover_letter", "cover_letter": "resume"}
    items: list[tuple[str, str, list[str], str]] = []
    seen: set[tuple[str, int, int]] = set()
    for d in out.claims:
        source = d.source_doc
        m = find_quote(d.text, docs[source])
        if m is None:
            m = find_quote(d.text, docs[other[source]])
            if m is None:
                issues.append(f"서류에 없는 주장이라 제외: {d.text!r}")
                continue
            issues.append(f"서류 구분 정정 ({source} → {other[source]}): {d.text!r}")
            source = other[source]
        key = (source, m.start, m.end)
        if key in seen:
            issues.append(f"중복 주장 제외: {m.text!r}")
            continue
        types = list(dict.fromkeys(d.types))[:3]
        if not types:
            issues.append(f"유형이 없어 제외: {m.text!r}")
            continue
        seen.add(key)
        items.append((source, m.text, types, (d.experience or "").strip() or "기타"))  # 원문 글자로 저장
        if len(items) >= MAX_CLAIMS:
            issues.append(f"주장이 많아 앞의 {MAX_CLAIMS}개만 사용")
            break
    return items


_SKILL_HEAD = re.compile(
    r"^(?:기술|기술 ?스택|보유 ?기술|사용 ?기술|주요 ?기술|스킬|skills?|tech(?:nical)? ?stack)\s*(?:[:：]\s*(\S.*))?$", re.I)


def skill_list_claims(resume_text: str, drafts: list, issues: list[str]) -> list[tuple[str, str, list[str], str]]:
    """이력서의 기술 목록 줄("기술: Python, FastAPI …" 또는 "기술 스택" 아래 글머리표 줄)을 TECH 주장으로 덧붙입니다.

    LLM 은 기술 나열을 주장으로 뽑지 않으므로(검증할 내용이 없음), 그대로 두면 "Python 활용 능력" 같은
    요구사항이 "서류에 근거 없음"이 됩니다. 이 주장은 연결 근거로만 쓰고 검증 포인트에는 넣지 않습니다.
    """
    lines, in_section = [], False
    for raw in resume_text.splitlines():
        line = raw.strip()
        if m := _SKILL_HEAD.match(line):
            in_section = not m.group(1)
            if m.group(1):
                lines.append(line)  # 한 줄짜리: "기술: ..." 전체
            continue
        if in_section and line[:1] in ("-", "•", "·"):
            lines.append(line.lstrip("-•· ").strip())
        else:
            in_section = False
    taken = [normalize(t) for src, t, *_ in drafts if src == "resume"]
    items = []
    for line in lines:
        n = normalize(line)
        if len(n) < 8 or any(n in t or t in n for t in taken):
            continue
        items.append(("resume", line, ["TECH"], "기타"))
        issues.append(f"기술 목록 줄을 연결용 주장으로 추가: {line!r}")
    return items


_METRIC = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|개|명|배|초|건|시간|일)")
_ROLE = re.compile(r"주도|리드|팀장|총괄|담당했")
_DECISION = re.compile(r"결정|선택")
_COLLAB = re.compile(r"제안|합의|협업|조율")


def fallback_claims(docs: dict[str, str]) -> list[tuple[str, str, list[str], str]]:
    """LLM 없이: 수치·역할·결정·협업 단서가 있는 문장을 주장으로 뽑습니다."""
    items = []
    for source, text in docs.items():
        for sent in re.split(r"(?<=[.!?다])\s+|\n", text):
            s = sent.strip(" -•·")
            types = [t for t, rx in (("METRIC", _METRIC), ("ROLE", _ROLE), ("DECISION", _DECISION), ("COLLAB", _COLLAB)) if rx.search(s)]
            if types and find_quote(s, text):
                items.append((source, s, types, "기타"))
    return items[:MAX_CLAIMS]


# ================================================================ 3. 요구사항 ↔ 주장 연결


def link(llm: JsonLLM, requirements: list[Requirement], claims: list[Claim], report: AnalysisReport) -> list[RequirementLink]:
    issues = report.issues.setdefault("link", [])
    try:
        out, _ = llm.generate_json(ROLE, P.LINKS_SYSTEM, P.build_links_prompt(requirements, claims, report.skill_claim_ids),
                                   P.LinksOutput)
        return sanitize_links(out, requirements, claims, issues)
    except Exception as e:
        issues.append(f"LLM 실패: {e} → 규칙 기반 대체값 사용")
        report.fallbacks.append("link")
        return fallback_links(requirements, claims)


def sanitize_links(out: P.LinksOutput, requirements: list[Requirement], claims: list[Claim], issues: list[str]) -> list[RequirementLink]:
    req_ids = [r.requirement_id for r in requirements]
    claim_ids = {c.claim_id for c in claims}
    by_req: dict[str, list[str]] = {}
    for d in out.links:
        if d.requirement_id not in req_ids:
            issues.append(f"없는 요구사항 ID 제외: {d.requirement_id!r}")
            continue
        kept = by_req.setdefault(d.requirement_id, [])
        for cid in d.claim_ids:
            if cid not in claim_ids:
                issues.append(f"없는 주장 ID 제외 ({d.requirement_id}): {cid!r}")
            elif cid not in kept:
                kept.append(cid)
    missing = [rid for rid in req_ids if rid not in by_req]
    if missing:
        issues.append(f"연결 결과가 빠진 요구사항은 '근거 없음'으로 채움: {missing}")
    # 요구사항마다 정확히 하나씩, 요구사항 순서대로
    return [RequirementLink(requirement_id=rid, claim_ids=by_req.get(rid, [])) for rid in req_ids]


_TECH_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+.#-]{1,}")


def fallback_links(requirements: list[Requirement], claims: list[Claim]) -> list[RequirementLink]:
    """LLM 없이: 영문 기술 용어(RAG, LangGraph, FastAPI …)가 겹치면 연결합니다."""
    words = {c.claim_id: {w.lower() for w in _TECH_WORD.findall(c.text)} for c in claims}
    links = []
    for r in requirements:
        rw = {w.lower() for w in _TECH_WORD.findall(r.text)}
        links.append(RequirementLink(requirement_id=r.requirement_id,
                                     claim_ids=[cid for cid, cw in words.items() if rw & cw]))
    return links


# ================================================================ 4. 검증 포인트


def checkpoints(llm: JsonLLM, requirements: list[Requirement], claims: list[Claim], experiences: dict[str, str],
                report: AnalysisReport) -> list[Checkpoint]:
    issues = report.issues.setdefault("checkpoints", [])
    try:
        out, _ = llm.generate_json(ROLE, P.CHECKPOINTS_SYSTEM,
                                   P.build_checkpoints_prompt(requirements, claims, experiences), P.CheckpointsOutput)
        cps = sanitize_checkpoints(out, claims, issues)
    except Exception as e:
        issues.append(f"LLM 실패: {e}")
        cps = []
    if not cps and claims:
        report.fallbacks.append("checkpoints")
        issues.append("유효한 검증 포인트 없음 → 규칙 기반 대체값 사용")
        cps = fallback_checkpoints(claims)
    return cps


def sanitize_checkpoints(out: P.CheckpointsOutput, claims: list[Claim], issues: list[str]) -> list[Checkpoint]:
    claim_ids = {c.claim_id for c in claims}
    kept: list[tuple[int, list[str], str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for d in out.checkpoints:
        ids = [cid for cid in dict.fromkeys(d.claim_ids) if cid in claim_ids]
        if len(ids) < len(d.claim_ids):
            issues.append(f"없는 주장 ID 제거 ({d.title}): {[c for c in d.claim_ids if c not in claim_ids]}")
        title, what = (d.title or "").strip(), (d.what_to_verify or "").strip()
        if not ids or not title or not what:
            issues.append(f"근거 주장이나 내용이 없어 제외: {d.title!r}")
            continue
        key = tuple(sorted(ids))
        if key in seen:
            issues.append(f"같은 주장 묶음의 중복 제외: {title!r}")
            continue
        seen.add(key)
        kept.append((PRIORITY_ORDER[d.priority], ids, title[:40], what[:300]))
    kept.sort(key=lambda x: x[0])  # 중요한 것부터 (질문 생성이 앞에서부터 쓰도록). 같은 우선순위는 LLM 순서 유지
    if len(kept) > MAX_CHECKPOINTS:
        issues.append(f"검증 포인트가 많아 앞의 {MAX_CHECKPOINTS}개만 사용")
    return [
        Checkpoint(checkpoint_id=f"CP-{i:03d}", claim_ids=ids, title=title, what_to_verify=what)
        for i, (_, ids, title, what) in enumerate(kept[:MAX_CHECKPOINTS], 1)
    ]


_FALLBACK_CP = {
    "METRIC": ("수치 성과의 측정 기준", "수치를 어떤 기준과 데이터로 측정했는지, 개선 전후 값은 무엇인지 확인합니다."),
    "ROLE": ("본인 역할의 구체 내용", "본인이 직접 내린 결정과 맡은 작업이 무엇인지 확인합니다."),
    "DECISION": ("결정의 근거", "그 선택을 한 이유와 검토한 대안을 확인합니다."),
    "TECH": ("기술 주장의 이해도", "그 기술을 쓴 이유와 동작 방식을 설명할 수 있는지 확인합니다."),
}


def fallback_checkpoints(claims: list[Claim]) -> list[Checkpoint]:
    cps = []
    for c in claims:
        for t in c.types:
            if t in _FALLBACK_CP and len(cps) < MAX_CHECKPOINTS:
                title, what = _FALLBACK_CP[t]
                cps.append(Checkpoint(checkpoint_id=f"CP-{len(cps) + 1:03d}", claim_ids=[c.claim_id], title=title, what_to_verify=what))
                break
    return cps


# ================================================================ 전체 실행


def run_analysis(
    llm: JsonLLM,
    resume_text: str,
    job_posting_text: str,
    job_description_text: str,
    cover_letter_text: str,
    on_step: StepCallback | None = None,
) -> AnalysisReport:
    """준비 파이프라인. 문서 추출과 read_posting/read_resume 은 서로 독립이라 동시에 실행합니다."""
    step = on_step or (lambda *_: None)
    report = AnalysisReport(analysis=Analysis(requirements=[], claims=[], checkpoints=[], links=[]))

    step("read_posting", "RUNNING", None)
    step("read_resume", "RUNNING", None)
    with ThreadPoolExecutor(2) as pool:
        f_req = pool.submit(read_postings, llm, job_posting_text, job_description_text, report)
        f_claim = pool.submit(read_resume, llm, resume_text, cover_letter_text, report)
        requirements = f_req.result()
        report.analysis = Analysis(requirements=requirements, claims=[], checkpoints=[], links=[])
        step("read_posting", "DONE", report.details["read_posting"])
        claims, experiences = f_claim.result()
    report.analysis = Analysis(requirements=requirements, claims=claims, checkpoints=[], links=[])
    step("read_resume", "DONE", report.details["read_resume"])

    step("link", "RUNNING", None)
    links = link(llm, requirements, claims, report)
    step("link", "DONE", None)

    step("checkpoints", "RUNNING", None)
    verifiable = [c for c in claims if c.claim_id not in report.skill_claim_ids]  # 기술 목록 줄은 검증할 내용이 없음
    cps = checkpoints(llm, requirements, verifiable, experiences, report)
    step("checkpoints", "DONE", None)

    report.analysis = Analysis(requirements=requirements, claims=claims, checkpoints=cps, links=links)

    step("competency_questions", "RUNNING", None)
    try:
        node_result = build_competency_question_node(llm)({"analysis": report.analysis})
        report.competency_question_status = node_result["competency_question_status"]
        report.competency_questions = node_result["competency_questions"]
        report.competency_question_reasons = node_result["competency_question_reasons"]
        reason = node_result["competency_question_reason"]
        if report.competency_question_status == "insufficient_analysis":
            report.issues.setdefault("competency_questions", []).append(reason)
        detail = f"인성·역량 질문 {len(report.competency_questions)}개 선택" if report.competency_questions else reason
    except Exception as e:
        report.competency_question_status = "insufficient_analysis"
        report.competency_questions = []
        report.issues.setdefault("competency_questions", []).append(f"질문 선택 실패: {e}")
        detail = "인성·역량 질문 선택 실패"
    step("competency_questions", "DONE", detail)

    step("technical_questions", "RUNNING", None)
    try:
        node_result = build_technical_question_node(llm)({"analysis": report.analysis})
        report.technical_question_status = node_result["technical_question_status"]
        report.technical_questions = node_result["technical_questions"]
        reason = node_result["technical_question_reason"]
        if report.technical_question_status == "insufficient_analysis":
            report.issues.setdefault("technical_questions", []).append(reason)
        detail = f"기술 질문 {len(report.technical_questions)}개 생성" if report.technical_questions else reason
    except Exception as e:
        report.technical_question_status = "insufficient_analysis"
        report.technical_questions = []
        report.issues.setdefault("technical_questions", []).append(f"질문 생성 실패: {e}")
        detail = "기술 질문 생성 실패"
    step("technical_questions", "DONE", detail)

    for name, msgs in report.issues.items():
        for msg in msgs:
            log.info("[%s] %s", name, msg)
    return report
