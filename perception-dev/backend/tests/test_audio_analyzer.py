from app.perception.audio_analyzer import analyze_audio_text


def test_analyze_audio_text() -> None:
    result = analyze_audio_text("하나 둘 셋 넷", 30)
    assert result.eojeol_count == 4
    assert result.speech_rate == 8.0


def test_zero_duration() -> None:
    result = analyze_audio_text("하나 둘", 0)
    assert result.speech_rate == 0

