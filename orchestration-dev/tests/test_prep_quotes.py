"""원문 인용 검증 규칙 테스트 (LLM 호출 없음)."""

from __future__ import annotations

from backend.interview.quotes import compact_len, contains, find_quote

SOURCE = "처음에는 재료 이름이 조금만 달라도 엉뚱한 레시피가 검색됐는데, 검색 정확도를 30% 개선했습니다."


def test_exact_quote_is_found_with_original_offsets():
    m = find_quote("검색 정확도를 30% 개선했습니다", SOURCE)
    assert m is not None
    assert SOURCE[m.start:m.end] == m.text
    assert m.text.startswith("검색") and m.text.endswith("니다")


def test_punctuation_and_spacing_differences_are_ignored():
    # STT 원문처럼 문장부호가 없고 띄어쓰기가 다른 경우
    assert find_quote("검색정확도를 30 개선했습니다.", SOURCE) is not None
    # LLM 이 문장부호를 덧붙인 경우
    assert find_quote("“검색 정확도를 30% 개선했습니다!”", SOURCE) is not None


def test_unclosed_bracket_in_match_is_closed():
    src = "- Gemini 임베딩과 ChromaDB로 레시피 의미 검색 구현 (986개 인덱싱)\n- 다음 줄"
    m = find_quote("의미 검색 구현 (986개 인덱싱", src)
    assert m is not None and m.text.endswith("인덱싱)")
    # 괄호가 원래 닫혀 있거나 없으면 그대로
    assert find_quote("레시피 의미 검색 구현", src).text == "레시피 의미 검색 구현"


def test_changed_number_is_not_found():
    # 숫자가 바뀌면 다른 주장이므로 절대 통과시키지 않습니다 (유사 매칭 금지)
    assert find_quote("검색 정확도를 50% 개선했습니다", SOURCE) is None


def test_paraphrase_is_not_found():
    assert find_quote("검색 정확도를 크게 높였습니다", SOURCE) is None


def test_too_short_quote_is_rejected():
    assert compact_len("레시피가") < 8
    assert find_quote("레시피가", SOURCE) is None
    # 기준을 낮추면 찾을 수 있음 (호출하는 쪽에서 명시적으로 선택)
    assert find_quote("레시피가", SOURCE, min_chars=1) is not None


def test_empty_values_are_safe():
    assert find_quote("", SOURCE) is None
    assert find_quote("검색 정확도를 30% 개선했습니다", None) is None
    assert contains(None, SOURCE) is False


def test_contains_for_short_names():
    jd = "회사: 브라이트런\n직무: AI Agent·LLM 애플리케이션 엔지니어"
    assert contains("브라이트런", jd)
    assert contains("ai agent llm", jd)  # 대소문자와 문장부호 무시
    assert not contains("넥스트웨이브", jd)
