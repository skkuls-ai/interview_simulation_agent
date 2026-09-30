"""인용 찾기 (임시 구현). 규칙은 B(경빈)가 정하고, 확정되면 이 함수만 B 의 validators 로 바꾼다.

약속한 모양: find_quote(인용, 원문) -> (start, end) 또는 None
지금 규칙: 원문에 글자 그대로 있어야 한다. 앞뒤 공백만 무시. 8자 미만은 거부 (A 의 quotes.py 기준).
"""

from __future__ import annotations

from collections.abc import Callable

MIN_QUOTE_CHARS = 8

QuoteFinder = Callable[[str, str], "tuple[int, int] | None"]


def find_quote(quote: str, source: str) -> tuple[int, int] | None:
    q = quote.strip()
    if len(q.replace(" ", "")) < MIN_QUOTE_CHARS or not source:
        return None
    i = source.find(q)
    return (i, i + len(q)) if i >= 0 else None
