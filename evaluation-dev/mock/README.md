# report.json mock (담당 E, W-14)

`GET /api/interviews/{id}/report` 응답 예시다. 화면 7(D, E)과 피드백 생성 코드(E)가 같은 모양으로 개발하도록 먼저 고정한다. 최종 위치는 `shared/mock/`이고, 변경은 C 리뷰 후 머지한다(docs/07).

| 파일 | 내용 | 용도 |
| --- | --- | --- |
| `report.json` | 정상 흐름. 판정이 섞인 결과 | 화면 7 기본 개발, 발표 데모 화면 |
| `report_edge.json` | 예외 상태를 모은 것 | 화면 7 예외 처리 개발 |
| `build_report_mock.py` | 두 파일을 만드는 스크립트와 계약 검사 | 답변이나 문구를 고칠 때 이 파일을 고치고 다시 실행 |

```bash
python evaluation-dev/mock/build_report_mock.py     # 두 파일 생성, 검사 통과 여부 출력
```

## 시나리오

A의 데모 샘플(가상 지원자 김하늘, 가상 회사 브라이트런)을 기준으로 했다. 질문 5개는 A ↔ B 연결 규칙 초안대로 만들었다. B의 `session_ready.json`이 나오면 질문 문장을 맞춘다.

| 질문 | 연결 | 답변 설계 | 결과 |
| --- | --- | --- | --- |
| Q-1 자기소개 | CP-001 | 20% 개선을 말하지만 기준은 말하지 않음 | 강점 위주 |
| Q-2 인성 | 인재상 RQ-011 | 실패 사례를 모아 원인을 찾고 수치로 확인 | 좋은 답변 |
| Q-3 인성 | CP-004 | 리드 역할이 모호하고 「것 같습니다」로 흐림 | 태도 조언의 말투 인용 |
| Q-4 기술 | CP-001, CP-002 | 지표를 모르고, 데이터가 「천 개 정도」라고 말함 (자소서는 약 5,000개) | 직무 적합성과 일관성 둘 다 보완 필요 |
| Q-5 기술 | 근거 없는 요구사항 RQ-005 | 경험 없이 방향만 설명, 90초에서 끊김 | 시간 초과 1회 |

- **직무 적합성** `NEEDS_WORK`: 검색 지표(RQ-014), LLM 품질 평가(RQ-005)
- **답변 일관성** `NEEDS_WORK`: 데이터 규모(CL-004 약 5,000개와 답변의 천 개 정도, CL-003 1,000개)
- **태도**: 판정과 점수 없음. 측정값과 조언 3개

## 코드가 계산한 값

- 인용 `start`, `end`: 답변 원문에서 찾은 위치. `answer_text[start:end] == text`
- 군말: 어, 음, 저기, 뭐랄까만 센다. 「그」는 세지 않는다 (9/29 STT 테스트)
- 분당 단어 수 `words_per_min`: 공백 기준 어절 수 ÷ 답변 시간(분) (docs/archive/perception-integration-guide.md 정의). 답변 시간은 9/29 실측 속도(90초 녹음 146어절, 분당 97어절)에 맞춤
- 시선: `measurable=true`인 질문의 정면 유지 비율 평균, 이탈 횟수 합계
- 시간 초과 횟수와 질문별 시간

## 계약서에 없는 부분 (제안, C 리뷰 필요)

docs/04 "확인 필요" 4, 10, 11번을 이렇게 채웠다.

| 항목 | 제안 |
| --- | --- |
| `requirements` 동봉 | `job_fit.refs`의 `RQ-` 문구를 화면에 그리기 위해 `questions`, `claims`, `checkpoints`처럼 함께 내려준다. 필드: `requirement_id`, `text`, `kind` |
| `requirements`, `claims`, `checkpoints` 범위 | 리포트에서 참조한 ID만 담는다 |
| `time.per_question` | 질문 5개 모두 담는다 |
| 인식 실패 질문 (`report_edge.json`의 Q-3) | `answer_text=null`, 말투 계산(분당 어절, 군말)에서 제외, `per_question`은 `strengths`와 `gaps`를 빈 목록으로 두고 `next_action`에 안내 문구. 연결 정보는 유지 |
| 판단 보류 (`report_edge.json`의 일관성) | `verdict=WITHHELD`, `quotes`와 `refs`는 빈 목록, `reason`에 보류 이유 |
| 카메라 측정 불가 | `gaze`의 `measurable=false`, 나머지 두 값은 `null` (프런트 `frontend/src/perception/types.ts`의 `DeliveryMetrics`와 같음) |

## 검사하는 규칙

`build_report_mock.py`가 만들 때마다 확인한다.

- 인용이 답변 원문의 그 위치에 실제로 있다 (T-201, T-202), `quote_id`는 `QT-` + 3자리이고 중복이 없다
- `refs`, `linked_claim_ids`, `linked_checkpoint_ids`가 동봉한 목록에 있다 (T-203)
- 판정이 `WITHHELD`가 아니면 인용이 1개 이상 있다
- 태도에 판정과 점수가 없다 (T-214)
- 피드백 문장에 금지 표현(합격, 채용 점수, 상위 몇 %, 자신감, 진실성 등)이 없다 (T-013)
- 주장과 요구사항 문장이 A의 데모 서류 원문에 그대로 있다 (T-204, 서류 파일이 옆에 있을 때)

## 주의

- `RQ-`, `CL-`, `CP-` 번호는 mock용이다. `CL-`, `CP-`는 A의 정답 라벨 순서(C1~C11, CP1~CP7)를 따랐고, `RQ-`는 A의 실제 분석 결과가 나오면 맞춘다.
- 판정 이유, 조언, 질문별 피드백 문구는 LLM이 쓸 내용을 사람이 대신 쓴 예시다. 프롬프트를 만들 때 문체 기준으로 쓴다.
