"""원문 인용 검증 (backend/interview/quotes.py 복사본. 이 폴더만 옮겨도 동작하도록 둠. E 의 인용 검증기(W-14)와 합칠 예정).

LLM 이 "원문에서 그대로 복사했다"고 낸 문장이 실제로 원문에 있는지 코드로 확인합니다.
분석 단계(서류 인용)와 평가 단계(답변 인용)가 같은 규칙을 씁니다.

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


def _compact(text: str) -> tuple[str, list[int]]:
    """비교용 문자열과, 그 글자 하나하나가 원문의 몇 번째 글자였는지의 목록."""
    chars: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        if _KEEP.match(ch):
            low = ch.lower()
            chars.append(low if len(low) == 1 else ch)
            index.append(i)
    return "".join(chars), index


def compact_len(text: str | None) -> int:
    return len(_compact(normalize(text))[0])


def find_quote(quote: str | None, source: str | None, min_chars: int = MIN_QUOTE_CHARS) -> QuoteMatch | None:
    """quote 가 source 안에 있으면 원문 기준 위치를 돌려줍니다. 없거나 너무 짧으면 None."""
    q, _ = _compact(normalize(quote))
    if len(q) < min_chars:
        return None
    src = normalize(source)
    s, index = _compact(src)
    pos = s.find(q)
    if pos < 0:
        return None
    start, end = index[pos], index[pos + len(q) - 1] + 1
    # 비교는 글자만 하지만, 원문 구간이 "(986개 인덱싱" 처럼 괄호가 한쪽만 남지 않게 닫는 기호를 붙입니다.
    for open_, close in _PAIRS:
        if src.count(open_, start, end) > src.count(close, start, end) and src[end:end + 1] == close:
            end += 1
    return QuoteMatch(start=start, end=end, text=src[start:end])


def contains(fragment: str | None, source: str | None) -> bool:
    """짧은 이름(회사명 등)이 원문에 있는지. 길이 제한 없이 같은 정규화 규칙으로 비교합니다."""
    f, _ = _compact(normalize(fragment))
    return bool(f) and f in _compact(normalize(source))[0]
