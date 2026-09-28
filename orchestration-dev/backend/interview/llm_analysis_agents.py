"""분석 에이전트 LLM 구현 (담당 1).

AnalysisAgents 인터페이스(agents.py)를 그대로 지키며, 구현한 메서드만 LLM 으로 바꾸고
나머지는 스텁을 상속해 씁니다 (HybridInterviewAgents 와 같은 방식).

현재 LLM 으로 구현한 메서드
- analyze_jd           : 채용공고 → 회사 정보, 요구사항
- analyze_experiences  : 이력서, 자기소개서 → 경험 (서류별로 따로)

LLM 출력은 그대로 믿지 않고 코드 안전장치를 거칩니다.
- 원문 인용이 해당 서류에 없으면 그 항목을 버립니다 (지어낸 요구사항, 경험 차단).
- 주장 구절(claimed_results)은 원문에서 찾은 것만, 원문 글자 그대로 저장합니다.
- 역량 코드는 문항 은행에 있는 것만 남깁니다.
- ID(R1, E1 …)는 코드가 순서대로 붙입니다.
- 호출이 실패하거나 남은 항목이 없으면 스텁 결과로 대체해 그래프가 멈추지 않게 합니다.
"""

from __future__ import annotations

import logging

from ..llm.client import CallInfo, JsonLLM, LLMError
from ..question_bank.models import QuestionBank
from .agents import StubAnalysisAgents
from .blueprint import CompanyContext, Experience, JDRequirement
from .prompts import analysis as P
from .quotes import contains, find_quote, normalize

log = logging.getLogger(__name__)

ROLE = "analysis"  # llm/settings.py 의 역할 (품질 우선, 면접 전 백그라운드)


class LLMAnalysisAgents(StubAnalysisAgents):
    MAX_REQUIREMENTS = 20  # 담당 업무, 자격, 우대, 인재상을 모두 담을 수 있게 (인재상은 역량 질문 선정에 쓰임)
    MAX_EXPERIENCES = 12
    MAX_CLAIMS_PER_EXPERIENCE = 6

    def __init__(self, llm: JsonLLM, bank: QuestionBank):
        self.llm = llm
        self.bank = bank
        self.competencies: list[P.Competency] = [
            (c.code, c.name, c.description) for cat in bank.categories for c in cat.competencies
        ]
        self.valid_codes = {code for code, _, _ in self.competencies}
        # 평가 스크립트와 디버깅용. 세션 간에 공유되므로 로직에는 쓰지 않습니다.
        self.last_calls: dict[str, CallInfo | None] = {}
        self.last_issues: dict[str, list[str]] = {}

    # ------------------------------------------------------------ JD 분석

    def analyze_jd(self, jd_text: str) -> tuple[CompanyContext, list[JDRequirement]]:
        name = "analyze_jd"
        try:
            out, info = self.llm.generate_json(
                ROLE, P.JD_SYSTEM, P.build_jd_prompt(jd_text, self.competencies), P.JDAnalysisOutput
            )
        except LLMError as e:
            return self._fallback(name, f"LLM 실패: {e}", lambda: super(LLMAnalysisAgents, self).analyze_jd(jd_text))

        company, reqs, issues = self.sanitize_jd(out, jd_text)
        if not reqs:
            return self._fallback(
                name, "원문과 일치하는 요구사항이 없음", lambda: super(LLMAnalysisAgents, self).analyze_jd(jd_text),
                info, issues,
            )
        self._record(name, info, issues)
        return company, reqs

    def sanitize_jd(
        self, out: P.JDAnalysisOutput, jd_text: str
    ) -> tuple[CompanyContext, list[JDRequirement], list[str]]:
        issues: list[str] = []
        reqs: list[JDRequirement] = []
        seen: set[tuple[int, int, str]] = set()

        for d in out.requirements:
            m = find_quote(d.source_quote, jd_text)
            if m is None:
                issues.append(f"공고에 없는 인용이라 요구사항 제외: {d.text!r} / {d.source_quote!r}")
                continue
            text = (d.text or "").strip() or m.text
            key = (m.start, m.end, normalize(text))
            if key in seen:
                issues.append(f"중복 요구사항 제외: {text!r}")
                continue
            seen.add(key)
            codes = self._valid_codes(d.competency_codes, issues, where=text)
            reqs.append(JDRequirement(
                id=f"R{len(reqs) + 1}", text=text[:80], kind=d.kind, importance=d.importance, competency_codes=codes,
            ))
            if len(reqs) >= self.MAX_REQUIREMENTS:
                issues.append(f"요구사항이 많아 앞의 {self.MAX_REQUIREMENTS}개만 사용")
                break

        company = CompanyContext(
            company_name=self._name_in(out.company_name, jd_text, issues, "회사 이름"),
            role_title=self._name_in(out.role_title, jd_text, issues, "직무 이름"),
            mission_or_values=[v.strip() for v in out.mission_or_values if v and v.strip()][:5],
            business_summary=(out.business_summary or "").strip() or None,
        )
        return company, reqs, issues

    # ------------------------------------------------------------ 경험 분석

    def analyze_experiences(self, resume_text: str | None, cover_letter_text: str | None) -> list[Experience]:
        name = "analyze_experiences"
        if not (resume_text or "").strip() and not (cover_letter_text or "").strip():
            self._record(name, None, [])
            return []
        stub = lambda: super(LLMAnalysisAgents, self).analyze_experiences(resume_text, cover_letter_text)  # noqa: E731
        try:
            out, info = self.llm.generate_json(
                ROLE, P.EXPERIENCE_SYSTEM,
                P.build_experience_prompt(resume_text, cover_letter_text, self.competencies),
                P.ExperienceAnalysisOutput,
            )
        except LLMError as e:
            return self._fallback(name, f"LLM 실패: {e}", stub)

        exps, issues = self.sanitize_experiences(out, resume_text, cover_letter_text)
        if not exps:
            return self._fallback(name, "원문과 일치하는 경험이 없음", stub, info, issues)
        self._record(name, info, issues)
        return exps

    def sanitize_experiences(
        self, out: P.ExperienceAnalysisOutput, resume_text: str | None, cover_letter_text: str | None
    ) -> tuple[list[Experience], list[str]]:
        docs = {"resume": resume_text or "", "cover_letter": cover_letter_text or ""}
        other = {"resume": "cover_letter", "cover_letter": "resume"}
        issues: list[str] = []
        exps: list[Experience] = []
        seen: set[tuple[str, str]] = set()

        for d in out.experiences:
            title = (d.title or "").strip()
            summary = (d.summary or "").strip()
            if not title or not summary:
                issues.append(f"제목이나 요약이 비어 경험 제외: {title!r}")
                continue

            # 경험이 실제로 그 서류에 있는지. 서류 구분만 틀렸으면 바로잡습니다.
            source = d.source
            if find_quote(d.source_quote, docs[source]) is None:
                if find_quote(d.source_quote, docs[other[source]]) is not None:
                    issues.append(f"서류 구분 정정 ({source} → {other[source]}): {title!r}")
                    source = other[source]
                else:
                    issues.append(f"서류에 없는 인용이라 경험 제외: {title!r} / {d.source_quote!r}")
                    continue

            key = (source, normalize(title))
            if key in seen:
                issues.append(f"같은 서류의 중복 경험 제외: {title!r}")
                continue
            seen.add(key)

            claims: list[str] = []
            for c in d.claimed_results:
                m = find_quote(c, docs[source])
                if m is None:
                    issues.append(f"서류에 없는 주장 구절 제외 ({title}): {c!r}")
                elif m.text not in claims:
                    claims.append(m.text)  # LLM 이 옮긴 글자가 아니라 원문 글자를 저장

            exps.append(Experience(
                id=f"E{len(exps) + 1}", source=source, title=title[:60],
                organization=(d.organization or "").strip() or None, period=(d.period or "").strip() or None,
                summary=summary[:300], claimed_results=claims[: self.MAX_CLAIMS_PER_EXPERIENCE],
                competency_codes=self._valid_codes(d.competency_codes, issues, where=title),
            ))
            if len(exps) >= self.MAX_EXPERIENCES:
                issues.append(f"경험이 많아 앞의 {self.MAX_EXPERIENCES}개만 사용")
                break
        return exps, issues

    # ------------------------------------------------------------ 공통

    def _valid_codes(self, codes: list[str], issues: list[str], where: str) -> list[str]:
        out: list[str] = []
        for c in codes:
            c = (c or "").strip()
            if c not in self.valid_codes:
                issues.append(f"없는 역량 코드 제거 ({where}): {c!r}")
            elif c not in out:
                out.append(c)
        return out[:3]

    @staticmethod
    def _name_in(name: str | None, source: str, issues: list[str], label: str) -> str | None:
        name = (name or "").strip()
        if not name:
            return None
        if not contains(name, source):
            issues.append(f"공고에 없는 {label}이라 비움: {name!r}")
            return None
        return name

    def _record(self, name: str, info: CallInfo | None, issues: list[str]) -> None:
        self.last_calls[name] = info
        self.last_issues[name] = issues
        for msg in issues:
            log.info("[%s] %s", name, msg)

    def _fallback(self, name, reason, stub_call, info: CallInfo | None = None, issues: list[str] | None = None):
        log.warning("[%s] %s → 스텁 결과 사용", name, reason)
        self._record(name, info, [*(issues or []), f"{reason} → 스텁 결과 사용"])
        return stub_call()
