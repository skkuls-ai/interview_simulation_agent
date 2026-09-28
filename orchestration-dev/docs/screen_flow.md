# 화면 흐름과 백엔드 연결

React 화면은 백엔드가 돌려주는 `prompt.type` 하나로 무엇을 보여줄지 정합니다.
화면이 판단할 것은 타이머와 장치뿐이고, 진행 순서는 모두 백엔드가 정합니다.

## 1. 전체 흐름

| # | 화면 | 들어가는 조건 | 사용자 행동 | 호출 API |
|---|---|---|---|---|
| 1 | 첫 화면 | 앱 시작, 면접 종료 후 | 새 면접 / 이어하기 / 이전 결과 보기 | `GET /sessions`, `GET /results` |
| 2 | 개인정보 동의 | 새 면접 | 항목별 동의 (마이크 필수) | `GET /consent`, `POST /sessions` |
| 3 | 서류 업로드 | 문서 동의함 | JD, 이력서, 자소서 업로드 (건너뛰기 가능) | `POST /sessions/{id}/documents` |
| 4 | AI 분석 중 | 업로드 완료 또는 건너뜀 | 대기 | `POST /sessions/{id}/analyze` |
| 5 | 면접 구성 안내 | 분석 완료 | 확인 | 응답의 `guide` 표시 |
| 6 | 카메라, 마이크 점검 | 안내 확인 | 마이크 음량, 얼굴 인식 확인 | 브라우저 안에서만 처리 |
| 7 | 준비시간 | `await_ready` | 자유롭게 준비 후 "면접 시작" | `POST /sessions/{id}/start` → `actions {action:"start"}` |
| 8 | 질문 화면 | `await_answer` | 답변 후 "답변 완료" | `actions {text, answer_duration_sec, sequence, speech, vision}` |
| 9 | 면접관 대기 | 답변 완료 직후 | 대기 | (응답 올 때까지) |
| 10 | 무응답 안내 | `no_response` | 다시 답변 / 넘어가기 | `actions {choice}` |
| 11 | 결과 정리 중 | 마무리 답변 직후 | 대기 | 응답에 `completed` 포함 |
| 12 | 종합 평가와 피드백 | `completed` | 확인 후 첫 화면 | - |

비전 관찰(MediaPipe)은 7번에서 "면접 시작"을 누른 순간 시작하고, 12번에 들어가면 멈춥니다.

## 2. 질문 화면 (`await_answer`) 타이머

```
[질문 표시 + TTS 재생: lead_in → text]
        │ 재생 끝
        ▼
[준비시간 5초 카운트다운]      ← think_time_sec, 모든 질문(자기소개, 꼬리질문, 마무리 포함)
        │ 0초
        ▼
[답변시간 00:00 → 01:00]       ← 이 시점부터 answer_duration_sec 측정
        │ 1분 경과
        ▼
[경고 표시 + 초과 시간 +00:23 …] ← soft_limit_sec. 녹음은 계속, 끊지 않음
        │ "답변 완료" 클릭
        ▼
[면접관 대기]
```

- 화면에는 `text`만 크게 보여주고, `lead_in`은 음성으로만 읽거나 작게 보여줍니다.
- 영역 이름은 어디에도 표시하지 않습니다. 진행 표시는 `sequence`(몇 번째 질문 화면인지)만 씁니다.
- `resumed: true`면 "이어서 진행합니다" 배지를 붙입니다.

## 3. 오류와 재전송

- 답변을 보낼 때 그 질문 화면의 `sequence`를 함께 보냅니다. 같은 요청이 두 번 도착해도 한 번만 기록됩니다.
- `503` 응답은 일시적 오류(LLM 호출 실패 등)입니다. 면접관 대기 화면을 유지한 채 같은 요청을 다시 보내면 멈춘 지점부터 이어서 처리합니다.
- `400`은 사용자에게 보여줄 안내 문구, `422`는 현재 단계와 맞지 않는 요청입니다.

## 4. 무응답

STT 결과가 비어 있으면 백엔드가 `no_response`를 돌려줍니다. 화면은 "다시 답변하시겠어요?"와 두 버튼을 보여줍니다.

- 다시 답변: 같은 질문이 "괜찮습니다. 준비되시면 다시 답변해 주세요."와 함께 다시 나오고, 준비시간 5초부터 다시 시작합니다.
- 넘어가기: 본 질문이면 그 문항은 1점(근거 없음) 처리하고 다음 질문으로 넘어갑니다.

## 5. 면접관 대기

답변 완료를 누른 순간부터 다음 응답이 올 때까지 "면접관이 답변 내용을 정리하고 있습니다"를 보여줍니다.
REST 에서는 화면이 요청을 보내면서 직접 띄우고, WebSocket 단계에서는 서버가 `interviewer_thinking` 이벤트를 보냅니다.

## 6. 중단 후 재개

첫 화면의 "이어하기" → `GET /sessions/{id}/resume` 의 `steps`를 순서대로 보여줍니다.

1. 이전 면접을 이어서 진행합니다 (본 질문 N개 완료, 답변 시간 사용량과 남은 시간)
2. 카메라와 마이크를 다시 확인합니다 (6번 화면 재사용)
3. 단계별 안내
   - 질문 중이었다면: 중단된 질문을 처음부터 다시 받습니다. 그때 답변은 저장되지 않았습니다.
   - 준비시간이었다면: 면접 구성 안내부터 다시 봅니다.
   - 결과 정리 중이었다면: `POST /sessions/{id}/finish` 호출
4. `next_prompt`로 면접 재개 (질문이면 "이어서 진행하겠습니다. 방금 드린 질문 다시 말씀드리겠습니다." 멘트)

진행 기록은 24시간 동안만 보관되며, 지나면 문서와 함께 삭제되어 이어할 수 없습니다.

## 7. 결과 화면 구성 (`completed.detail`)

| 영역 | 데이터 | 비고 |
|---|---|---|
| 종합 판정 | `chro_decision` | 합격, 보류, 불합격과 규칙별 통과 여부. 모순된 답변이나 판단 보류 문항이 있으면 최대 보류 |
| 자기소개 | `final_feedback.intro_feedback` | 합불 미반영. 이 회사여야 하는 이유, 포부, 경험 적합성과 개선 가이드 |
| 역량별 피드백 | `final_feedback.improvements`, `evaluations` | 체크포인트 근거 인용 |
| 시간 관리 | `final_feedback.time_management.messages` | 장황했던 답변 목록, 못 물은 영역 |
| 다음 면접 대비 | `final_feedback.follow_up_risks` | 모순(INCONSISTENT) 답변. 다음 면접에서 추가 질문을 받을 수 있다는 안내 |
| 답변 품질 분포 | `final_feedback.answer_quality` | SUFFICIENT, OFF_TOPIC, INCONSISTENT, PARTIAL, VAGUE 문항 수 |
| 문항별 평가 | `evaluations[*].status`, `panel` | 평가자 3명 점수, 의견 차이(disputed), 판단 보류(undetermined) 표시 |
| 비언어 코칭 | `final_feedback.nonverbal_tips` | 카메라 동의 시에만 |
| 다시 연습할 문항 | `next_practice_question_ids` | |

`completed.stored`가 false면 "이 결과는 저장되지 않습니다" 안내를 함께 보여줍니다.
