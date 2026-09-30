"""문서·답변에서 원문 인용을 찾고 원문 기준 위치를 계산합니다.

현재는 문서 분석 단계에서 요구사항·주장 인용을 검증하는 데 사용합니다.

규칙
- 공백, 줄바꿈, 문장부호를 모두 지우고 비교합니다. STT 원문에는 문장부호가 거의 없고,
  LLM 은 인용할 때 문장부호를 붙이거나 빼는 일이 많기 때문입니다.
- 공백과 문장부호를 뺀 길이가 MIN_QUOTE_CHARS 미만이면 근거로 인정하지 않습니다 (우연히 일치할 수 있음).
- 비슷한 문장을 찾아 통과시키는 방식(fuzzy matching)은 쓰지 않습니다. 있거나 없거나 둘 중 하나입니다.
- 위치(start, end)는 LLM 이 준 값을 믿지 않고 여기서 원문 기준으로 다시 계산합니다.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MIN_QUOTE_CHARS = 8

# 한글, 영문, 숫자만 남깁니다. \w 는 한글을 포함하지만 '_' 도 포함하므로 따로 뺍니다.
_KEEP = re.compile(r"[^\W_]")
_PAIRS = [("(", ")"), ("[", "]"), ("“", "”"), ("‘", "’")]


@dataclass(frozen=True)
class QuoteMatch:
    start: int
    end: int
    text: str  # 원문에서 실제로 잘라낸 구간


def normalize(text: str | None) -> str:
    return unicodedata.normalize("NFC", text or "")


def _hangul_jamo(ch: str) -> str | None:
    codepoint = ord(ch)
    if 0x1100 <= codepoint <= 0x115F or 0xA960 <= codepoint <= 0xA97C:
        return "L"
    if 0x1160 <= codepoint <= 0x11A7 or 0xD7B0 <= codepoint <= 0xD7C6:
        return "V"
    if 0x11A8 <= codepoint <= 0x11FF or 0xD7CB <= codepoint <= 0xD7FB:
        return "T"
    return None


def _has_no_hangul_final(ch: str) -> bool:
    codepoint = ord(ch)
    return 0xAC00 <= codepoint <= 0xD7A3 and (codepoint - 0xAC00) % 28 == 0


def _compact(text: str) -> tuple[str, list[int], list[int]]:
    """NFC 비교 문자열과 각 문자의 원문 시작·끝 위치를 돌려줍니다."""
    chars: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    i = 0
    while i < len(text):
        start = i
        cluster = [text[i]]
        first = text[i]
        first_jamo = _hangul_jamo(first)
        i += 1

        if first_jamo == "L" and i < len(text) and _hangul_jamo(text[i]) == "V":
            cluster.append(text[i])
            i += 1
            if i < len(text) and _hangul_jamo(text[i]) == "T":
                cluster.append(text[i])
                i += 1
        elif _has_no_hangul_final(first) and i < len(text) and _hangul_jamo(text[i]) == "T":
            cluster.append(text[i])
            i += 1

        while i < len(text) and unicodedata.category(text[i]).startswith("M"):
            cluster.append(text[i])
            i += 1

        for normalized in unicodedata.normalize("NFC", "".join(cluster)):
            if _KEEP.match(normalized):
                low = normalized.lower()
                chars.append(low if len(low) == 1 else normalized)
                starts.append(start)
                ends.append(i)
    return "".join(chars), starts, ends


def compact_len(text: str | None) -> int:
    return len(_compact(text or "")[0])


def find_quote(quote: str | None, source: str | None, min_chars: int = MIN_QUOTE_CHARS) -> QuoteMatch | None:
    """quote 가 source 안에 있으면 원문 기준 위치를 돌려줍니다. 없거나 너무 짧으면 None."""
    q, _, _ = _compact(quote or "")
    if len(q) < min_chars:
        return None
    src = source or ""
    s, starts, ends = _compact(src)
    pos = s.find(q)
    if pos < 0:
        return None
    start, end = starts[pos], ends[pos + len(q) - 1]
    # 비교는 글자만 하지만, 원문 구간이 "(986개 인덱싱" 처럼 괄호가 한쪽만 남지 않게 닫는 기호를 붙입니다.
    for open_, close in _PAIRS:
        if src.count(open_, start, end) > src.count(close, start, end) and src[end:end + 1] == close:
            end += 1
    return QuoteMatch(start=start, end=end, text=src[start:end])


def contains(fragment: str | None, source: str | None) -> bool:
    """짧은 이름(회사명 등)이 원문에 있는지. 길이 제한 없이 같은 정규화 규칙으로 비교합니다."""
    f, _, _ = _compact(fragment or "")
    return bool(f) and f in _compact(source or "")[0]
