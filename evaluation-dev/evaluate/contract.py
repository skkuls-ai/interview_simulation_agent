"""docs/04 계약 모델 임시 복사본 (태도 측정값 계산에 필요한 부분만).

C 의 schemas/state.py 가 올라오면 이 파일을 지우고 import 를 그쪽으로 바꾼다.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class DeliveryMetrics(BaseModel):  # 프런트가 계산해 보냄 (D), 점수 미반영
    measurable: bool
    frontal_ratio: Optional[float] = None  # 0~1, 정면 유지 비율
    gaze_away_count: Optional[int] = None


class Answer(BaseModel):
    question_id: str
    transcript: Optional[str] = None
    transcript_status: Literal["PENDING", "DONE", "NO_SPEECH", "FAILED"] = "PENDING"
    duration_sec: float
    timed_out: bool
    delivery: Optional[DeliveryMetrics] = None
    words_per_min: Optional[float] = None  # 코드가 transcript 에서 계산 (Should)
    filler_count: Optional[int] = None  # 코드가 transcript 에서 계산 (Should)
