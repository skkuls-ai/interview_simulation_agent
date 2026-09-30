# evaluation-dev (담당 E, 임시 폴더)

C의 저장소 뼈대(W-02, W-03)가 올라오기 전까지 쓰는 독립 폴더다. 뼈대가 올라오면 아래처럼 옮기고 import만 바꾼다.

| 지금 | 옮길 곳 | 내용 |
| --- | --- | --- |
| `evaluate/attitude.py` | `backend/app/nodes/evaluate/attitude.py` | 태도 측정값 계산 |
| `evaluate/contract.py` | 삭제, `backend/app/schemas/state.py`로 교체 | docs/04 계약 모델 임시 복사본 |
| `tests/test_attitude.py` | `backend/tests/` | 단위 테스트 25개 |
| `mock/report.json`, `mock/report_edge.json` | `shared/mock/` (C 리뷰) | 화면 7용 mock (W-14) |
| `mock/build_report_mock.py` | `shared/mock/` 또는 `scripts/` | mock 생성과 계약 검사 |

```bash
pip install pydantic pytest
python -m pytest -q tests             # 25 passed
python mock/build_report_mock.py      # mock 두 개 생성 + 검사
```

## 태도 측정값 (`evaluate/attitude.py`)

`attitude_metrics(answers)`가 리포트의 `attitude.metrics`를 만든다. LLM을 쓰지 않는다. mock의 측정값도 이 함수로 계산하므로 mock과 실제 결과가 같은 규칙을 따른다.

| 값 | 규칙 | 근거 |
| --- | --- | --- |
| 군말 `filler_count` | 어, 음, 저기, 뭐랄까. 앞뒤가 한글이 아닐 때만 셈("어떤", "음식", "저기압"은 제외). 「그」는 세지 않음 | 9/29 STT 테스트: 받아쓰기 모델이 군말 8개 중 8개를 남김. 「그」는 쉼표가 사라져 "그 과정" 같은 일반 표현과 구분 불가 |
| 분당 단어 수 `words_per_min` | 공백 기준 어절 수 합계 ÷ 답변 시간 합계(분), 정수 반올림 | perception 가이드 정의. 9/29 90초 녹음으로 확인: 146어절, 분당 97.3 |
| 말투 계산 대상 | 받아쓰기가 된 답변(`DONE`)만. 인식 실패(`NO_SPEECH`, `FAILED`)는 제외 | (제안) docs/04 확인 필요 10번 |
| 시선 `frontal_ratio` | `measurable=true`인 답변만, 답변 시간으로 가중 평균 | 짧은 답변과 긴 답변이 같은 비중이 되지 않도록 |
| 시선 `gaze_away_count` | 측정된 답변의 이탈 횟수 합계 | |
| 측정 불가 | 측정된 답변이 없으면 `measurable=false`, 나머지 `null` | perception 계약과 같음 |
| 시간 | 질문 5개 모두, 시간 초과 횟수 | 인식 실패 질문도 시간 목록에는 넣음 |

- `enrich(answer)`: State의 `Answer.words_per_min`, `Answer.filler_count`를 채운다. C가 STT 직후에 부를지, E가 평가 시작 때 부를지는 C ↔ E에서 정한다.
- `FILLER_RE`, `FILLER_WORDS`: 인용 검증(B)에서 군말을 빼고 비교할 때 같은 목록을 쓰도록 공개해 둠.
- 시선 값은 참고 측정값이다. 판정이나 다른 영역 평가에 넘기지 않는다(T-213).

## D에게 확인 중 (답에 따라 조언 문구만 바뀜, 계산 코드는 그대로)

- `gaze_away_count` 1회의 기준(몇 초 이상 벗어나면 1회)
- 시선 측정 구간(녹음 중만인지)
- `duration_sec` 시작 시점(5초 대기 후 녹음 시작부터인지)
