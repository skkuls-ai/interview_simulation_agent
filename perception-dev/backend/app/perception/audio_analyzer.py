import re

from .schemas import AudioMetrics


def analyze_audio_text(transcript: str, duration_seconds: float) -> AudioMetrics:
    """공백 기준 어절 수와 답변 전체 시간 기준 속도를 계산한다."""
    eojeol_count = len(re.findall(r"\S+", transcript.strip()))
    speech_rate = eojeol_count / (duration_seconds / 60) if duration_seconds > 0 else 0.0
    return AudioMetrics(eojeol_count=eojeol_count, speech_rate=round(speech_rate, 1))

