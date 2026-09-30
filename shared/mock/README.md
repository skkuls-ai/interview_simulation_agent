# shared/mock 안내

한 줄 요약: 실제 API가 준비되기 전에 프런트와 백엔드 단위 테스트가 함께 쓰는 고정 데모 JSON 7개와 사용 규칙.
기준: Claude Docs 2026-09-29 버전 (「개발 계약·담당표」 개발 계약 4)

관련 문서: docs/04-api-schema.md (API·스키마), docs/05-architecture.md (구성), docs/07-dev-rules.md (개발 규칙), docs/08-test-scenarios.md (테스트)

## 고정 데모 시나리오

- 발표 데모 샘플 지원자A(가상의 신입 지원자, 실제 인물·회사 없음), 세션 하나: `session_id = S-3f2a9c1e` (9/30 C 결정)
- 서류에 「RAG 검색 정확도를 20% 개선」이라는 경험 주장이 있고(CL-001), Q-1(자기소개)과 Q-4(기술) 답변이 이 주장과 연결된다.
- 채용공고의 우대 사항 LangGraph가 RQ-004이며, 직무 적합성 판정(NEEDS_WORK)의 근거가 된다. 답변 일관성은 SUFFICIENT(서류와 어긋나는 내용 없음).
- 질문 5개는 Q-1 INTRO, Q-2 BEHAVIOR, Q-3 BEHAVIOR, Q-4 TECH, Q-5 TECH 고정 순서. Q-3은 1분 30초 초과(timed_out)로 넘어간 사례.

## 파일별 용도

| 파일 | 어느 API 응답인가 | 상태 | 작성 담당 | 용도 |
|---|---|---|---|---|
| `sample_inputs.json` | (응답 아님) `POST /api/interviews` 요청 값 | - | A | 고정 데모 서류 4종 텍스트(`resume_text`, `job_posting_text`, `job_description_text`, `cover_letter_text`)와 `privacy_consent`. 채용공고에 인재상 문단 포함. LLM 분석 프롬프트 시험과 화면 2 자동 입력에 쓴다. |
| `session_preparing.json` | `GET /api/interviews/{id}` | PREPARING | A | 화면 3 단계 진행 표시. steps 6개 중 2개 DONE, 1개 RUNNING. `questions`는 null. |
| `session_ready.json` | `GET /api/interviews/{id}` | READY | B | 화면 3 완료 → 4·5. 질문 5개(`question_id`, `order`, `type`, `text`만). 기대 요소·평가 기준·연결 정보는 넣지 않는다. |
| `answer_accepted.json` | `POST /api/interviews/{id}/answers` | IN_PROGRESS / EVALUATING | C | 응답 두 가지를 한 파일에 담는다. `in_progress` = Q-2 접수(다음 Q-3), `last` = Q-5 접수(`next_question_id`가 null, status가 EVALUATING). HTTP 202. |
| `session_evaluating.json` | `GET /api/interviews/{id}` | EVALUATING | C | 화면 6 단계 진행 표시(transcribe, attitude, job_fit, consistency, compose). |
| `report.json` | `GET /api/interviews/{id}/report` | COMPLETED | E | 화면 7 전체. 영역 3개, 질문별 피드백, 화면이 다른 API를 부르지 않도록 `questions`·`requirements`·`claims`·`checkpoints` 동봉. `backend/scripts/build_report_mock.py`로 생성. |
| `report_edge.json` | `GET /api/interviews/{id}/report` | COMPLETED | E | 화면 7 예외 상태 확인용. Q-3 답변 인식 안 됨(`answer_text` null), 카메라 측정 불가(`gaze.measurable` false), 답변 일관성 WITHHELD. |

`report.json` 안의 인용(`quotes`)은 모두 `questions[].answer_text`에 실제로 있는 문장이며, `start`·`end`는 그 답변 텍스트의 글자 위치다(0부터, `end`는 포함하지 않음, 즉 `answer_text[start:end] == text`). 파이썬으로 검증했다.

## 프런트에서 mock으로 전환하기

프런트는 React + Vite를 가정한다(미정, 킥오프에서 확정). 환경변수 하나로 전환한다.

```bash
# frontend/.env.local (커밋 금지)
VITE_USE_MOCK=true    # mock JSON 사용
VITE_USE_MOCK=false   # 실제 백엔드 사용 (기본)
```

- Docker로 실행할 때 `VITE_USE_MOCK`은 프런트 이미지를 빌드할 때 정해진다. 값을 바꾸면 이미지를 다시 빌드해야 한다.
- 전환 로직은 `frontend/src/api/client.ts` 한 곳에만 둔다(담당 D). 화면 코드는 mock 여부를 모른다.
- mock 모드에서 `GET /api/interviews/{id}`는 화면 진행에 따라 `session_preparing.json` → `session_ready.json` → `session_evaluating.json` 순으로 돌려주고, `POST /answers`는 `answer_accepted.json`의 `in_progress`(Q-1~Q-4)와 `last`(Q-5)를, `GET /report`는 `report.json`을 돌려준다.
- `session_evaluating.json` 다음에 `report.json`이 나오는 시점(화면 6 → 7)은 client.ts에서 시간 지연으로 흉내 낸다.
- 백엔드 단위 테스트도 같은 파일을 읽는다. 구조가 달라지면 State/API 계약과 함께 고쳐야 한다.

## 답변이 인식되지 않은 질문의 응답 예 (NO_SPEECH / FAILED)

`transcript_status`가 `NO_SPEECH`(무음) 또는 `FAILED`(변환 실패)이면 면접은 그대로 진행하고, `POST /answers` 응답은 정상(202)이다. 리포트에서는 해당 질문의 `answer_text`가 null이고 판정에서 빠진다. 화면은 「답변이 기록되지 않았습니다」로 표시한다. 이 사례는 `report_edge.json`의 Q-3에 있다.

```json
{ "question_id": "Q-2", "type": "BEHAVIOR", "text": "...", "answer_text": null }
```

## 수정 규칙

1. `backend/app/schemas/`와 `shared/mock/` 변경은 통합 책임자 C가 리뷰한 뒤 머지한다.
2. 필드명을 바꾸려면 팀 채널에 먼저 올리고, Claude Docs 「개발 계약·담당표」를 고친 뒤, 코드와 mock을 고친다.
3. 작성 담당(A, B, C, E)이 자기 파일을 고치되, 계약 변경이 섞이면 C가 함께 본다.
4. mock에는 실제 인물·회사·API 키를 넣지 않는다. 모든 JSON은 파싱 가능해야 한다.
   `python3 -c "import json;json.load(open('shared/mock/report.json'))"`
5. `report.json`을 고칠 때는 인용의 `start`·`end`를 다시 계산해 검증한다.
6. 상태값·열거값은 대문자 영어(READY 등), 필드명은 snake_case.

## 확인 필요

- `session_ready.json`의 `steps`에는 6단계를 모두 DONE으로 넣었는데, READY 이후에도 steps를 내려주는지 Docs에 명시가 없다. (Docs는 PREPARING과 EVALUATING의 steps만 정의)
- `session_evaluating.json`의 `detail` 문구(「답변 5개 변환 완료」)는 예시로 만든 값이다. Docs에는 화면 3의 detail 예시만 있다.
- 각 파일의 `steps[].label` 중 화면 6 문구는 Docs에서 「제안」으로 표시된 것이다.
- `report.json`의 `per_question[]`에는 5개 질문을 모두 넣었다. Docs 예시는 1개만 보여준다.
