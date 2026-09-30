"""코드 판정 규칙. LLM 출력을 검사해 (정리된 결과, 문제 목록)을 돌려준다.

문제 목록이 비어 있지 않으면 러너가 그 호출만 이유를 넘겨 1회 재평가한다.
재평가 뒤에도 남은 문제는 finalize_* 가 규칙대로 정리한다 (근거 없는 판정은 WITHHELD 등).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ...validators import quotes as V
from .prompts import AttitudeOut, FitOut, PerQuestionOut, QuestionOut, QuoteRef

# 인용 찾기: (인용, 답변 원문) -> 원문 기준 (start, end) 또는 None. 테스트에서 바꿔 끼울 수 있게 함수로 받음
QuoteFinder = Callable[[str, str], "tuple[int, int] | None"]


def find_quote(quote: str, source: str) -> tuple[int, int] | None:
    """validators/quotes.py(A, B 공용) 규칙: 공백과 문장부호를 빼고 비교, 8자 미만 거부, 위치는 원문 기준으로 다시 계산."""
    m = V.find_quote(quote, source)
    return (m.start, m.end) if m else None

# T-013 금지 표현 (임시 목록, B 의 검사가 나오면 교체)
FORBIDDEN_RE = re.compile(r"합격|불합격|채용 점수|상위 ?\d+ ?%|자신감|진실성|거짓말|긴장|불안")
# 코칭 규칙 (prompts COMMON 8, 9, PER_QUESTION): 솔직히 말한 한계를 숨기라는 조언, 서류에 말을 맞추라는 조언,
# 질문별 피드백의 어조·확신 평가. 걸리면 재평가 사유로 넘기고, 남으면 그 문장을 뺀다.
_LIMIT = r"(한계|약점|부족한 ?점|모르는 ?(것|부분)|경험이 없|못했다는|않았다는|없다는|써 ?보지 못|해 ?보지 않)"
_HIDE = r"((언급|말하|밝히|드러내|꺼내|말은|얘기는|이야기는).{0,8}(없이|말고|않|마세요|줄이|빼|생략)|하지 말|빼고|생략)"
CONCEAL_RE = re.compile(_LIMIT + r".{0,15}" + _HIDE + r"|숨기|감추|둘러대|꾸며|포장해")
ALIGN_RE = re.compile(r"서류.{0,40}(일치하도록|일치시|맞춰 ?(말|답|두|보)|맞추도록)")
TONE_RE = re.compile(r"확신|자신 ?있게|당당하게|단호하게|어조|말투|목소리")
MAX_ADVICE = 3

WITHHELD_NO_EVIDENCE = "판단의 근거가 되는 답변 문장을 확인하지 못해 판단을 보류했습니다."
WITHHELD_TOO_FEW = "판단할 수 있는 답변이 부족해 판단을 보류했습니다."
WITHHELD_FAILED = "피드백을 만드는 중 문제가 생겨 판단을 보류했습니다."


@dataclass
class Located:
    question_id: str
    text: str
    start: int
    end: int


@dataclass
class FitResult:
    verdict: str
    reason: str
    quotes: list[Located] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)


@dataclass
class AttitudeResult:
    advice: list[str] = field(default_factory=list)
    quotes: list[Located] = field(default_factory=list)


def forbidden(text: str) -> str | None:
    m = FORBIDDEN_RE.search(text or "")
    return m.group(0) if m else None


def bad_advice(text: str, content_only: bool = False) -> str | None:
    """금지 표현(T-013)과 코칭 규칙 위반을 찾아 사유를 돌려준다. content_only: 질문별 피드백(어조·확신 평가도 금지)."""
    if word := forbidden(text):
        return f"금지 표현 '{word}'"
    if m := CONCEAL_RE.search(text or ""):
        return f"솔직히 말한 한계를 숨기라는 조언 '{m.group(0)}' (그 위에 더할 내용을 쓸 것)"
    if m := ALIGN_RE.search(text or ""):
        return f"서류에 말을 맞추라는 조언 '{m.group(0)}' (사실을 확인해 틀린 쪽을 바로잡으라고 쓸 것)"
    if content_only and (m := TONE_RE.search(text or "")):
        return f"질문별 피드백에 어조·확신 평가 '{m.group(0)}' (답변 내용에 무엇을 더할지 쓸 것)"
    return None


def locate(refs: list[QuoteRef], sources: dict[str, str], finder: QuoteFinder) -> tuple[list[Located], list[str]]:
    """인용마다 답변 원문에서 위치를 다시 찾는다. 없는 인용은 버리고 문제로 기록한다 (T-201, T-202)."""
    found, issues = [], []
    for r in refs:
        src = sources.get(r.question_id)
        pos = finder(r.text, src) if src is not None else None
        if pos is None:
            where = "인식된 답변이 없는 질문" if src is None else "답변 원문"
            issues.append(f"인용이 {where}에 없음 ({r.question_id}): '{r.text[:40]}'")
            continue
        start, end = pos
        found.append(Located(r.question_id, src[start:end], start, end))
    return found, issues


# ---------------------------------------------------------------- 직무 적합성, 답변 일관성


def check_fit(out: FitOut, sources: dict[str, str], allowed_refs: set[str], finder: QuoteFinder) -> tuple[FitResult, list[str]]:
    quotes, issues = locate(out.quotes, sources, finder)
    refs = []
    for ref in out.refs:
        if ref in allowed_refs:
            if ref not in refs:
                refs.append(ref)
        else:
            issues.append(f"refs 에 없는 ID: {ref}")  # T-203
    if word := forbidden(out.reason):
        issues.append(f"이유 문장에 금지 표현: {word}")
    if out.verdict != "WITHHELD" and not quotes:
        issues.append(f"{out.verdict} 판정에 근거 인용이 없음")
    return FitResult(out.verdict, out.reason, quotes, refs), issues


def finalize_fit(r: FitResult) -> FitResult:
    if forbidden(r.reason):
        return FitResult("WITHHELD", WITHHELD_FAILED)
    if r.verdict != "WITHHELD" and not r.quotes:
        return FitResult("WITHHELD", WITHHELD_NO_EVIDENCE)
    if r.verdict == "WITHHELD":
        return FitResult("WITHHELD", r.reason or WITHHELD_NO_EVIDENCE)
    return r


# ---------------------------------------------------------------- 태도


def check_attitude(out: AttitudeOut, sources: dict[str, str], finder: QuoteFinder) -> tuple[AttitudeResult, list[str]]:
    issues: list[str] = []
    if not out.advice:
        issues.append("조언이 없음")
    if len(out.advice) > MAX_ADVICE:
        issues.append(f"조언은 {MAX_ADVICE}개까지")
    result = AttitudeResult()
    for item in out.advice[:MAX_ADVICE]:
        if why := bad_advice(item.text):
            issues.append(f"조언에 {why}")
            continue
        quotes, qi = locate(item.quotes, sources, finder)
        issues += qi
        result.advice.append(item.text)
        result.quotes += quotes
    return result, issues


# ---------------------------------------------------------------- 질문별


def check_per_question(out: PerQuestionOut, expected_qids: list[str], known_claims: set[str]) -> tuple[dict[str, QuestionOut], list[str]]:
    issues: list[str] = []
    kept: dict[str, QuestionOut] = {}
    for item in out.items:
        if item.question_id not in expected_qids:
            issues.append(f"피드백 대상이 아닌 질문: {item.question_id}")
            continue
        if item.question_id in kept:
            issues.append(f"같은 질문을 두 번 씀: {item.question_id}")
            continue
        bad = [c for c in item.extra_claim_ids if c not in known_claims]
        if bad:
            issues.append(f"{item.question_id} 없는 주장 ID: {bad}")
        texts = [*item.strengths, *item.gaps, item.next_action]
        issues += [f"{item.question_id} 피드백에 {why}" for t in texts if (why := bad_advice(t, content_only=True))]
        kept[item.question_id] = item.model_copy(update={
            "extra_claim_ids": [c for c in item.extra_claim_ids if c in known_claims],
            "strengths": [s for s in item.strengths if not bad_advice(s, content_only=True)],
            "gaps": [g for g in item.gaps if not bad_advice(g, content_only=True)],
        })
    missing = [q for q in expected_qids if q not in kept]
    if missing:
        issues.append(f"피드백이 빠진 질문: {missing}")
    return kept, issues
