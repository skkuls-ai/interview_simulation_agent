"""질문 안전 검사. 면접 중 생성 질문과 분석 단계의 개인화 질문 모두에 씁니다."""

from __future__ import annotations

import re

from .blueprint import CATEGORY_NAMES

# 채용절차법(제4조의3) 수집 금지 항목과 차별 소지가 있는 주제
# (?<![가-힣]) 는 단어 중간 매칭을 막음: "향상시키는", "지식재산", "연세대" 같은 평범한 표현은 통과
FORBIDDEN = re.compile(
    r"(?<![가-힣])키(가|는|를)|체중|몸무게|외모|용모|출신 ?지역|출신지|고향|"
    r"혼인|결혼|배우자|애인|연애|임신|출산|자녀 ?계획|"
    r"부모님|아버지|어머니|(?<![가-힣])형제|(?<![가-힣])자매(?!결연)|가족.{0,4}(직업|학력|재산)|"
    r"(?<![가-힣])재산|(?<![가-힣])집안(?!일)|종교|정치(적)? ?(성향|견해|관)|지지 ?정당|"
    r"(?<![가-힣])나이|(?<![가-힣])연세(?!대)|몇 ?살"
)
MAX_QUESTION_CHARS = 120


def check_generated(text: str, max_chars: int = MAX_QUESTION_CHARS) -> str | None:
    """생성 질문의 문제를 찾아 이유를 돌려줍니다. 문제가 없으면 None."""
    t = text.strip()
    if not t:
        return "빈 질문"
    if len(t) > max_chars:
        return f"너무 긺 ({len(t)}자)"
    if m := FORBIDDEN.search(t):
        return f"금지 주제 ({m.group(0)})"
    if any(name in t for name in CATEGORY_NAMES.values()):
        return "평가 영역 이름 노출"
    if t.count("?") > 2:
        return "여러 질문을 한 번에 함"
    return None
