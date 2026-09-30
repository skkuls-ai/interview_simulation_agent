"""Validate quoted evidence against a candidate's answer transcript."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher

from ..interview.state import Quote

EVIDENCE_MATCH = 0.85
_FILLER_RE = re.compile(r"(?<!\w)(?:어|음|아)(?!\w)")


def _normalize_with_positions(text: str) -> tuple[str, list[int]]:
    fillers = [match.span() for match in _FILLER_RE.finditer(text)]
    normalized: list[str] = []
    positions: list[int] = []
    filler_index = 0

    for index, char in enumerate(text):
        while filler_index < len(fillers) and index >= fillers[filler_index][1]:
            filler_index += 1
        if filler_index < len(fillers) and fillers[filler_index][0] <= index < fillers[filler_index][1]:
            continue
        if char.isspace() or unicodedata.category(char).startswith("P"):
            continue
        folded = char.casefold()
        normalized.extend(folded)
        positions.extend([index] * len(folded))

    return "".join(normalized), positions


def find_quote_span(quote: str, source: str, threshold: float = EVIDENCE_MATCH) -> tuple[int, int] | None:
    """Return a source span for a quote, tolerating spacing, punctuation, and spoken fillers."""
    normalized_quote, _ = _normalize_with_positions(quote)
    normalized_source, positions = _normalize_with_positions(source)
    if len(normalized_quote) < 4 or not normalized_source:
        return None

    exact_start = normalized_source.find(normalized_quote)
    if exact_start >= 0:
        return positions[exact_start], positions[exact_start + len(normalized_quote) - 1] + 1

    allowance = max(1, math.ceil(len(normalized_quote) * (1 - threshold)))
    matcher = SequenceMatcher(None, normalized_quote, normalized_source, autojunk=False)
    candidate_starts: set[int] = set()
    for block in matcher.get_matching_blocks():
        if block.size:
            rough_start = block.b - block.a
            candidate_starts.update(
                start for start in range(rough_start - allowance, rough_start + allowance + 1)
                if 0 <= start < len(normalized_source)
            )

    best: tuple[float, int, int] | None = None
    min_length = max(1, len(normalized_quote) - allowance)
    max_length = len(normalized_quote) + allowance
    for start in candidate_starts:
        for length in range(min_length, min(max_length, len(normalized_source) - start) + 1):
            ratio = SequenceMatcher(
                None, normalized_quote, normalized_source[start:start + length], autojunk=False
            ).ratio()
            if ratio >= threshold and (best is None or ratio > best[0]):
                best = (ratio, start, length)

    if best is None:
        return None
    _, start, length = best
    return positions[start], positions[start + length - 1] + 1


def evidence_in(quote: str, source: str, threshold: float = EVIDENCE_MATCH) -> bool:
    return find_quote_span(quote, source, threshold) is not None


def validate_quotes(
    candidates: Iterable[str],
    source: str,
    question_id: str,
    start_index: int = 1,
    threshold: float = EVIDENCE_MATCH,
) -> list[Quote]:
    """Keep source-backed quotes, recalculate offsets, and issue sequential QT IDs."""
    if start_index < 1:
        raise ValueError("start_index must be positive")

    validated: list[Quote] = []
    seen_spans: set[tuple[int, int]] = set()
    next_index = start_index
    for candidate in candidates:
        span = find_quote_span(candidate, source, threshold)
        if span is None or span in seen_spans:
            continue
        if next_index > 999:
            raise ValueError("QT quote ID limit exceeded")
        start, end = span
        validated.append(Quote(
            quote_id=f"QT-{next_index:03d}",
            question_id=question_id,
            text=source[start:end],
            start=start,
            end=end,
        ))
        seen_spans.add(span)
        next_index += 1
    return validated