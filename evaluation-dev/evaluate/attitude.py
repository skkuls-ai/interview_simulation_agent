"""태도 영역 측정값 계산 (담당 E). LLM 을 쓰지 않는다.

리포트의 attitude.metrics 를 만든다.

    metrics = attitude_metrics(answers)
    # {"speech": {...}, "gaze": {...}, "time": {...}}  (shared/mock/report.json 과 같은 모양)

규칙
- 군말: 어, 음, 저기, 뭐랄까. 「그」는 세지 않는다 ("그 과정" 같은 일반 표현과 구분할 수 없어서).
  9/29 STT 테스트에서 받아쓰기 모델이 군말 8개 중 8개를 남기는 것을 확인했다.
- 분당 단어 수: 공백 기준 어절 수 ÷ 답변 시간(분). 한국어 단어 경계 대신 어절을 쓴다 (docs/archive/perception-integration-guide.md 정의).
- 말투 지표(분당 어절, 군말)는 받아쓰기가 된 답변(transcript_status=DONE)만 쓴다.
  답변 인식 실패(NO_SPEECH, FAILED) 질문은 빼고, 시간 목록에는 넣는다. (제안, docs/04 확인 필요 10)
- 시선: measurable=true 인 답변만 쓴다. 정면 유지 비율은 답변 시간으로 가중 평균, 이탈 횟수는 합계.
  측정된 답변이 하나도 없으면 measurable=false, 나머지는 null.
- D 와 확정한 기준 (9/30): 시선은 녹음 중에만 측정하고, duration_sec 도 5초 대기가 끝나고 녹음을 시작한
  시점부터 잰다. 그래서 측정 구간과 가중치가 같다. gaze_away_count 1회는 연속 1초 이상 카메라에서 벗어난 경우.
- 시선 값은 참고 측정값이다. 판정(verdict)이나 다른 영역 평가에 넘기지 않는다 (T-213).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .contract import Answer

FILLER_WORDS = ("어", "음", "저기", "뭐랄까")
# 앞뒤가 한글이 아닐 때만 군말로 본다: "어떤", "음식", "저기압" 은 세지 않음. "어어", "음..." 은 1회.
FILLER_RE = re.compile(r"(?<![가-힣])(어+|음+|저기|뭐랄까)(?![가-힣])")


def count_fillers(text: str | None) -> int:
    return len(FILLER_RE.findall(text or ""))


def find_fillers(text: str | None) -> list[str]:
    return FILLER_RE.findall(text or "")


def count_eojeol(text: str | None) -> int:
    return len((text or "").split())


def words_per_min(text: str | None, duration_sec: float) -> float | None:
    """한 답변의 분당 어절 수. 시간이 0 이하이거나 글자가 없으면 None."""
    n = count_eojeol(text)
    if duration_sec <= 0 or n == 0:
        return None
    return round(n / (duration_sec / 60), 1)


def _spoken(a: Answer) -> bool:
    return a.transcript_status == "DONE" and bool(a.transcript and a.transcript.strip())


def enrich(answer: Answer) -> Answer:
    """State.answers 의 words_per_min, filler_count 를 채운 사본. 받아쓰기가 없으면 None 으로 둔다."""
    if not _spoken(answer):
        return answer.model_copy(update={"words_per_min": None, "filler_count": None})
    return answer.model_copy(update={
        "words_per_min": words_per_min(answer.transcript, answer.duration_sec),
        "filler_count": count_fillers(answer.transcript),
    })


def speech_metrics(answers: Iterable[Answer]) -> dict:
    spoken = [a for a in answers if _spoken(a)]
    words = sum(count_eojeol(a.transcript) for a in spoken)
    minutes = sum(a.duration_sec for a in spoken) / 60
    return {
        "words_per_min": round(words / minutes) if minutes > 0 and words else None,
        "filler_count": sum(count_fillers(a.transcript) for a in spoken),
    }


def gaze_metrics(answers: Iterable[Answer]) -> dict:
    measured = [a for a in answers
                if a.delivery and a.delivery.measurable and a.delivery.frontal_ratio is not None]
    if not measured:
        return {"measurable": False, "frontal_ratio": None, "gaze_away_count": None}
    total = sum(a.duration_sec for a in measured)
    if total > 0:
        ratio = sum(a.delivery.frontal_ratio * a.duration_sec for a in measured) / total
    else:
        ratio = sum(a.delivery.frontal_ratio for a in measured) / len(measured)
    return {
        "measurable": True,
        "frontal_ratio": round(ratio, 2),
        "gaze_away_count": sum(a.delivery.gaze_away_count or 0 for a in measured),
    }


def time_metrics(answers: Iterable[Answer]) -> dict:
    answers = list(answers)
    return {
        "timed_out_count": sum(a.timed_out for a in answers),
        "per_question": [{"question_id": a.question_id, "duration_sec": round(a.duration_sec, 1),
                          "timed_out": a.timed_out} for a in answers],
    }


def attitude_metrics(answers: Iterable[Answer]) -> dict:
    """리포트의 attitude.metrics. 답변은 질문 순서대로 넘긴다."""
    answers = list(answers)
    return {"speech": speech_metrics(answers), "gaze": gaze_metrics(answers), "time": time_metrics(answers)}
