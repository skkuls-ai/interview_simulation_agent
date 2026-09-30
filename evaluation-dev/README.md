# evaluation-dev (담당 E, 임시 폴더)

C의 저장소 뼈대(W-02, W-03)가 올라오기 전까지 쓰는 독립 폴더다. 뼈대가 올라오면 아래처럼 옮기고 import만 바꾼다.

| 지금 | 옮길 곳 | 내용 |
| --- | --- | --- |
| `evaluate/attitude.py` | `backend/app/nodes/evaluate/attitude.py` | 태도 측정값 계산 |
| `evaluate/contract.py` | 삭제, `backend/app/schemas/state.py`로 교체 | docs/04 계약 모델 임시 복사본 |
| `evaluate/runner.py`, `rules.py`, `prompts.py`, `quotes.py` | `backend/app/nodes/evaluate/` | 피드백 생성 러너, 코드 판정 규칙, 프롬프트 초안, 인용 찾기(임시) |
| `evaluate/llm/` | C의 LLM 클라이언트로 교체하거나 `backend/app/llm/` | orchestration의 Gemini 클라이언트 복사본 (역할별 모델) |
| `tests/test_attitude.py`, `tests/test_runner.py` | `backend/tests/` | 단위 테스트 44개 (API 호출 없음) |
| `scripts/run_demo_eval.py` | `scripts/` | 데모 시나리오로 실제 Gemini 피드백 1회 실행 |
| `mock/report.json`, `mock/report_edge.json` | `shared/mock/` (C 리뷰) | 화면 7용 mock (W-14) |
| `mock/build_report_mock.py` | `shared/mock/` 또는 `scripts/` | mock 생성과 계약 검사 |

```bash
pip install pydantic pytest
python -m pytest -q tests             # 44 passed
python scripts/run_demo_eval.py --fake   # LLM 없이 흐름 확인
python scripts/run_demo_eval.py          # 실제 Gemini (gcloud 로그인, GOOGLE_CLOUD_PROJECT 필요)
python mock/build_report_mock.py      # mock 두 개 생성 + 검사
```

## 피드백 생성 러너 (`evaluate/runner.py`)

9/30 결정한 A 구조: 영역별로 한 번에 판정하고, 최종 판정은 코드 규칙으로 확정한다.

```
태도 측정값 (코드) ─┐
                    ├─ LLM 4개 동시: 태도 조언, 직무 적합성, 답변 일관성, 질문별 피드백(5개 한 번에)
                    ├─ 코드 검증 → 판정 영역 둘이 끝나는 즉시 검증 에이전트 1회 (질문별 피드백과 겹쳐 실행)
                    ├─ 무효인 호출만 이유를 넘겨 1회 재평가 → 코드 검증 → 검증 에이전트
                    └─ 규칙대로 정리, QT- 발급, Report 조립 (report.json 모양)
```

정상일 때 LLM 호출 5회(평가 4 + 검증 1), 재평가가 모두 일어나면 최대 10회.

| 역할 (`INTERVIEW_MODEL_<역할>`) | 대상 | 모델, 추론 수준 | 제한 시간 |
| --- | --- | --- | --- |
| `evaluator` | 직무 적합성, 답변 일관성 | gemini-3.8-flash, MEDIUM | 60초, 재시도 2 |
| `coach` | 태도 조언, 질문별 피드백 | gemini-3.8-flash, LOW | 45초, 재시도 2 |
| `validator` | 검증 에이전트 (판정 영역만) | gemini-3.8-flash, LOW | 15초, 재시도 없음. 넘기면 코드 검증 결과로 진행 |

429(호출 한도) 오류가 나면 2초 기다렸다가 다시 시도한다. 9/30 실측(3회, 중앙값 40.6초)에서 검증 에이전트가 3.7 Flash 429로 30초까지 늦어진 것을 반영했다.

| 코드 규칙 | 내용 |
| --- | --- |
| 인용 검증 (T-201, T-202) | 원문에 없는 인용은 버리고 재평가 사유로 넘김. 위치는 코드가 다시 계산 |
| 근거 없는 판정 | 재평가 뒤에도 인용이 하나도 없으면 `WITHHELD` |
| 판정 가능한 답변 수 | 인식된 답변이 2개 미만이면 직무 적합성, 일관성은 LLM을 부르지 않고 `WITHHELD` |
| 참조 ID (T-203) | 목록에 없는 `RQ-`, `CL-`는 버림 |
| 인식 실패 (T-215) | LLM에 넘기지 않음. 질문별 피드백은 안내 문구, 연결 정보는 유지 |
| 금지 표현 (T-013) | 재평가 사유. 남으면 그 문장을 빼거나 `WITHHELD` |
| 시선 (T-213) | 태도 프롬프트에만 넣음. 시선 값이 달라도 판정이 같은지 테스트로 확인 |
| 실패 처리 | LLM이 두 번 실패하면 그 영역만 대체값. 검증 에이전트가 실패하면 코드 검증 결과로 진행 |

- 가짜 LLM이 mock 문구를 돌려주면 러너 결과가 `mock/report.json`과 완전히 같다 (테스트로 확인).
- 인용 찾기(`quotes.py`)와 금지 표현 목록(`rules.py`)은 임시 구현이다. B의 인용 검증 규칙과 금지 표현 검사가 나오면 교체한다.
- 프롬프트(`prompts.py`)는 초안이다. 실제 Gemini 결과를 보고 다듬는다(5번 작업).

## 태도 측정값 (`evaluate/attitude.py`)

`attitude_metrics(answers)`가 리포트의 `attitude.metrics`를 만든다. LLM을 쓰지 않는다. mock의 측정값도 이 함수로 계산하므로 mock과 실제 결과가 같은 규칙을 따른다.

| 값 | 규칙 | 근거 |
| --- | --- | --- |
| 군말 `filler_count` | 어, 음, 저기, 뭐랄까. 앞뒤가 한글이 아닐 때만 셈("어떤", "음식", "저기압"은 제외). 「그」는 세지 않음 | 9/29 STT 테스트: 받아쓰기 모델이 군말 8개 중 8개를 남김. 「그」는 쉼표가 사라져 "그 과정" 같은 일반 표현과 구분 불가 |
| 분당 단어 수 `words_per_min` | 공백 기준 어절 수 합계 ÷ 답변 시간 합계(분), 정수 반올림 | docs/archive/perception-integration-guide.md 정의. 9/29 90초 녹음으로 확인: 146어절, 분당 97.3 |
| 말투 계산 대상 | 받아쓰기가 된 답변(`DONE`)만. 인식 실패(`NO_SPEECH`, `FAILED`)는 제외 | (제안) docs/04 확인 필요 10번 |
| 시선 `frontal_ratio` | `measurable=true`인 답변만, 답변 시간으로 가중 평균 | 짧은 답변과 긴 답변이 같은 비중이 되지 않도록 |
| 시선 `gaze_away_count` | 측정된 답변의 이탈 횟수 합계 | |
| 측정 불가 | 측정된 답변이 없으면 `measurable=false`, 나머지 `null` | 프런트 `frontend/src/perception/types.ts`의 `DeliveryMetrics`와 같음 |
| 시간 | 질문 5개 모두, 시간 초과 횟수 | 인식 실패 질문도 시간 목록에는 넣음 |

- `enrich(answer)`: State의 `Answer.words_per_min`, `Answer.filler_count`를 채운다. C가 STT 직후에 부를지, E가 평가 시작 때 부를지는 C ↔ E에서 정한다.
- `FILLER_RE`, `FILLER_WORDS`: 인용 검증(B)에서 군말을 빼고 비교할 때 같은 목록을 쓰도록 공개해 둠.
- 시선 값은 참고 측정값이다. 판정이나 다른 영역 평가에 넘기지 않는다(T-213).

## D와 확정한 기준 (9/30 도연 님 답변)

프런트 구현 위치: `feature/frontend`의 `frontend/src/perception/` (`config.ts`의 `gaze_away_min_ms: 1_000`, `types.ts`의 `DeliveryMetrics`). perception-dev 폴더는 없어졌다.

| 항목 | 기준 | 계산에 미치는 영향 |
| --- | --- | --- |
| `gaze_away_count` 1회 | 시선이 연속 1초 이상 카메라에서 벗어나면 1회 | 합계만 내므로 계산은 그대로. 조언 문구는 "1초 이상 시선이 벗어난 횟수"로 쓴다 |
| 시선 측정 구간 | 녹음 중에만. 질문 읽기와 5초 대기는 제외 | 측정 구간과 `duration_sec`가 같아서, 답변 시간으로 가중 평균하는 방식이 그대로 맞다 |
| `duration_sec` 시작 | 5초 대기가 끝나고 녹음을 시작한 시점부터 | 분당 어절 수의 분모가 실제 말한 구간과 같다. 말 사이 침묵은 포함된다 |
