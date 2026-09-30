"""태도 측정값 단위 테스트. 받아쓰기 예문은 9/29 STT 실측 결과(gemini-3.5-transcribe-preview) 그대로."""

import json
from pathlib import Path

import pytest

from app.nodes.evaluate.attitude import (
    attitude_metrics,
    count_eojeol,
    count_fillers,
    enrich,
    find_fillers,
    gaze_metrics,
    speech_metrics,
    words_per_min,
)
from app.schemas.state import Answer, DeliveryMetrics

# 3차: 군말 7개 대본 (어 3, 음 2, 그 1, 저기 1). 받아쓰기에서 "그,"의 쉼표가 사라짐
STT_SHORT = ("어, 안녕하세요. 저는 음, 사내 문서 검색 챗봇을 만든 지원자입니다. 그 프로젝트에서 저는 어, 검색 파이프라인을 맡았고요. "
             "음, 정확도를 20% 올렸습니다. 저기 청크 크기를 어, 여러 번 바꿔 봤습니다.")

# 4차: 90초 대본 (군말 8개: 어 4, 음 3, 저기 1), 90초에서 잘림
STT_90S = ("어, 네. 제가 가장 자신 있는 경험은 사내 규정 문서를 검색해 주는 RAG 챗봇 프로젝트입니다. 팀원 네 명이 함께했고 저는, 음, "
           "검색 파이프라인 설계와 평가를 맡았습니다. 처음에는 검색 결과가 질문과 잘 맞지 않아서, 어, 정확도가 기대보다 많이 낮았습니다. "
           "그래서 평가용 질문 50개를 먼저 만들고 상위 세 개 결과 안에 정답 문서가 들어오는 비율을 기준으로 삼았습니다. 음, 청크 크기는 "
           "팀원과 의견이 달랐는데요. 두 방식을 같은 질문으로 비교해서 결정했습니다. 결과는 작은 청크가 조금 더 나았고 저는, 어, 키워드 "
           "검색과 벡터 검색의 가중치를 조정하는 데 집중했습니다. 저기 가중치는 0.3부터 0.7까지 바꿔가며 실험했고요. 음, 최종적으로 "
           "정확도를 20% 올릴 수 있었습니다. 어, 이 과정에서 실험 결과를 팀 위키에 정리해서 다른 팀도 참고할 수 있게 했습니다. 앞으로는 "
           "검색 품질을 사람이 일일이 확인하지 않아도 되도록 평가 과정을 자동화하고 싶습니다. 새 문 문서가 들어올 때마다 평가 질문을 다시 "
           "돌려서 정확도가 떨어지는지 바로 알 수 있게 만드는 것이 목표입니다. 또 답변이 틀렸을 때 어떤 문서")


def ans(qid="Q-1", text="답변입니다", status="DONE", dur=30.0, timed_out=False, delivery=None):
    return Answer(question_id=qid, transcript=text, transcript_status=status, duration_sec=dur,
                  timed_out=timed_out, delivery=delivery)


def dm(ratio, away, measurable=True):
    return DeliveryMetrics(measurable=measurable, frontal_ratio=ratio if measurable else None,
                           gaze_away_count=away if measurable else None)


# ------------------------------------------------------------------ 군말


def test_fillers_match_9_29_transcripts():
    assert count_fillers(STT_90S) == 8
    assert sorted(find_fillers(STT_90S)) == sorted(["어"] * 4 + ["음"] * 3 + ["저기"])
    assert count_fillers(STT_SHORT) == 6  # 「그」는 세지 않으므로 7이 아니라 6


@pytest.mark.parametrize("text", ["어떤 문서", "음식 추천", "어제 회의", "음악을 들으며", "저기압", "뭐랄까요", "그 과정에서", "그래서"])
def test_ordinary_words_are_not_fillers(text):
    assert count_fillers(text) == 0


@pytest.mark.parametrize("text,n", [("어어, 그러니까", 1), ("음... 네", 1), ("어 음 저기 뭐랄까", 4), ("(어) 네", 1), ("", 0), (None, 0)])
def test_filler_variants(text, n):
    assert count_fillers(text) == n


# ------------------------------------------------------------------ 분당 어절


def test_eojeol_and_wpm_on_real_90s_recording():
    assert count_eojeol(STT_90S) == 146
    assert words_per_min(STT_90S, 90.0) == pytest.approx(97.3, abs=0.1)


def test_wpm_guards():
    assert words_per_min("", 30) is None
    assert words_per_min("말 합니다", 0) is None


def test_speech_uses_total_words_over_total_time_and_skips_unrecognized():
    answers = [ans("Q-1", "하나 둘 셋 넷 다섯 여섯", dur=6),  # 6어절 / 0.1분
               ans("Q-2", "하나 둘 셋 넷", dur=6),  # 4어절 / 0.1분
               ans("Q-3", None, status="NO_SPEECH", dur=12),
               ans("Q-4", "무시됨 무시됨", status="FAILED", dur=12)]
    assert speech_metrics(answers) == {"words_per_min": 50, "filler_count": 0}  # 10어절 / 0.2분


def test_speech_when_nothing_recognized():
    assert speech_metrics([ans(text=None, status="NO_SPEECH")]) == {"words_per_min": None, "filler_count": 0}


def test_enrich_fills_state_fields():
    a = enrich(ans(text=STT_90S, dur=90))
    assert a.filler_count == 8 and a.words_per_min == pytest.approx(97.3, abs=0.1)
    b = enrich(ans(text=None, status="NO_SPEECH"))
    assert b.filler_count is None and b.words_per_min is None


# ------------------------------------------------------------------ 시선


def test_gaze_weighted_by_duration_and_away_summed():
    g = gaze_metrics([ans(dur=30, delivery=dm(0.9, 1)), ans(dur=90, delivery=dm(0.5, 6))])
    assert g == {"measurable": True, "frontal_ratio": 0.6, "gaze_away_count": 7}  # (27+45)/120


def test_gaze_skips_unmeasurable_and_missing():
    g = gaze_metrics([ans(delivery=dm(0.8, 2)), ans(delivery=dm(None, None, measurable=False)), ans(delivery=None)])
    assert g == {"measurable": True, "frontal_ratio": 0.8, "gaze_away_count": 2}


def test_gaze_all_unmeasurable():
    g = gaze_metrics([ans(delivery=dm(None, None, measurable=False)), ans(delivery=None)])
    assert g == {"measurable": False, "frontal_ratio": None, "gaze_away_count": None}


# ------------------------------------------------------------------ 시간과 전체 모양


def test_time_keeps_all_questions_including_unrecognized():
    answers = [ans("Q-1", dur=34.6), ans("Q-2", None, status="NO_SPEECH", dur=12), ans("Q-5", dur=90, timed_out=True)]
    t = attitude_metrics(answers)["time"]
    assert t["timed_out_count"] == 1
    assert [p["question_id"] for p in t["per_question"]] == ["Q-1", "Q-2", "Q-5"]


def test_shape_matches_report_mock():
    mock = Path(__file__).parents[2] / "shared" / "mock" / "report.json"
    if not mock.exists():
        pytest.skip("shared/mock/report.json 없음")
    expected = json.loads(mock.read_text(encoding="utf-8"))["attitude"]["metrics"]
    got = attitude_metrics([ans(delivery=dm(0.8, 1))])
    assert {k: set(v) for k, v in got.items()} == {k: set(v) for k, v in expected.items()}
    assert set(got["time"]["per_question"][0]) == set(expected["time"]["per_question"][0])
