# nodes/evaluate (담당 E)

화면 6에서 피드백(태도, 직무 적합성, 답변 일관성, 질문별 상세)을 만든다. 결과는 `schemas.api.ReportResponse` 모양의 dict다.

## 평가 그래프에서 부르는 법

```python
from app.nodes.evaluate import evaluate_state

report = evaluate_state(state, llm, on_step=lambda step_id, st: ...)  # st: "RUNNING" / "DONE"
record.report_response = ReportResponse.model_validate(report)
```

- 부르는 시점: 답변 5개의 `transcript_status`가 모두 `PENDING`이 아니게 된 뒤 (STT 대기 제한 30초, 넘으면 `FAILED`로 두고 시작)
- `on_step`으로 화면 6의 `attitude`, `job_fit`, `consistency`, `compose` 단계를 기록한다. `transcribe`는 C의 몫
- `llm`: `llm/client.py`의 `GeminiClient(LLMSettings.from_env())`

## 네 단계를 러너 하나가 처리하는 이유

docs/05 10절은 노드 순서를 `graph/`에서 정하게 되어 있지만, 평가 네 단계는 이 러너가 동시에 처리한다(9/30 C와 확인 중).
순서대로 부르면 호출 시간이 모두 더해져 60초를 넘는다. 9/30 실측: 동시 실행과 검증 겹치기로 보통 11~15초.

```
태도 측정값 (코드) ─┐
                    ├─ LLM 4개 동시: 태도 조언, 직무 적합성, 답변 일관성, 질문별 피드백(5개 한 번에)
                    ├─ 판정 영역 둘이 끝나는 즉시 검증 에이전트 1회 (질문별 피드백과 겹쳐 실행)
                    ├─ 무효인 호출만 이유를 넘겨 1회 재평가
                    └─ 코드 규칙으로 정리, QT- 발급, 리포트 조립
```

## 파일

| 파일 | 내용 |
| --- | --- |
| `runner.py` | 러너, `evaluate_state()` 진입점, 호출 기록(`Trace`) |
| `rules.py` | 코드 판정 규칙: 인용 위치 검사, refs 검사, 근거 없으면 WITHHELD, 금지 표현 |
| `prompts.py` | 프롬프트와 LLM 출력 모양 (초안, 실측 보며 다듬는 중) |
| `attitude.py` | 태도 측정값 계산 (군말, 분당 어절, 시선, 시간). LLM 안 씀 |
| `quotes.py` | 인용 찾기 **임시 구현**. B의 `validators/` 인용 검증이 나오면 교체 |
| `llm/` | Gemini 클라이언트 (역할별 모델, 재시도, 429 대기). 공용 위치가 정해지면 이동 |

## 코드 판정 규칙

| 규칙 | 내용 |
| --- | --- |
| 인용 (T-201, T-202) | 원문에 없는 인용은 버리고 재평가 사유로 넘김. 위치는 코드가 다시 계산 |
| 근거 없는 판정 | 재평가 뒤에도 인용이 없으면 `WITHHELD` |
| 판정 가능한 답변 수 | 인식된 답변 2개 미만이면 직무 적합성, 일관성은 LLM 없이 `WITHHELD` |
| 참조 ID (T-203) | 목록에 없는 `RQ-`, `CL-`는 버림 |
| 인식 실패 (T-215) | LLM에 넘기지 않음. 질문별 피드백은 안내 문구, 연결 정보는 유지 |
| 금지 표현 (T-013) | 재평가 사유. 남으면 문장을 빼거나 `WITHHELD` (목록은 임시, B 검사로 교체) |
| 시선 (T-213) | 태도 프롬프트에만. 시선 값이 달라도 판정이 같은지 테스트로 확인 |
| 태도 (T-214) | 판정, 점수 없음 |

## 모델 (`.env`의 `INTERVIEW_MODEL_<역할>`)

| 역할 | 대상 | 기본 | 제한 |
| --- | --- | --- | --- |
| `evaluator` | 직무 적합성, 답변 일관성 | gemini-3.8-flash, MEDIUM | 60초 |
| `coach` | 태도 조언, 질문별 피드백 | gemini-3.8-flash, LOW | 45초 |
| `validator` | 검증 에이전트 | gemini-3.8-flash, LOW | 15초, 넘기면 코드 검증 결과로 진행 |

연결: `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global` (gcloud 로그인 또는 서비스 계정 키)

## 태도 측정값 규칙

- 군말: 어, 음, 저기, 뭐랄까. 「그」는 세지 않음 (9/29 STT 테스트)
- 분당 단어 수: 공백 기준 어절 수 ÷ 답변 시간(분)
- 말투 계산은 인식된 답변만, 시간 목록은 전체
- 시선: `measurable=true`인 답변만, 정면 유지 비율은 답변 시간 가중 평균, 이탈 횟수 합계. 1회 = 연속 1초 이상 이탈, 녹음 중에만 측정 (D와 확정)

## 테스트와 실측

```bash
cd backend
python -m pytest -q tests                    # E 50개 포함, API 호출 없음
python scripts/run_demo_eval.py --repeat 3   # 실제 Gemini (컨테이너 밖, gcloud 로그인 필요)
python scripts/build_report_mock.py          # shared/mock/report.json, report_edge.json 다시 생성
```

- 가짜 LLM이 mock 문구를 돌려주면 러너 결과가 `shared/mock/report.json`과 완전히 같다 (테스트로 확인). 화면 7을 mock으로 만들면 실제 결과에도 맞는다.
- 9/30 실측(데모 시나리오 7회): 판정 7/7 기대와 같음. 보통 11~15초, Gemini 쪽 지연이 걸린 호출이 있으면 40~50초 (제한 시간 조정 예정).
