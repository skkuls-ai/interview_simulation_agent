# 05. 아키텍처

한 줄 요약: 프런트(React+Vite 가정) - FastAPI - 준비·평가 그래프 - 외부 LLM/STT(/TTS) 구성과, LLM은 관찰·생성만 하고 코드가 계산·검증하는 책임 경계.
기준: Claude Docs 2026-09-29 버전 (「개발 계약·담당표」 탭, 「화면별 기능정의서」 탭)

관련 문서: docs/01-PRD.md, docs/02-screen-flow.md, docs/03-functional-spec.md, docs/04-api-schema.md, docs/06-wbs-schedule.md, docs/07-dev-rules.md, docs/08-test-scenarios.md

## 0. 미정 항목 (그림의 점선·주석)

| 항목 | 상태 | 표기 |
|---|---|---|
| 질문 음성(TTS): 브라우저 기능 vs 서버 모델(Vertex AI TTS) | 미정. 서버면 음성 반환 API가 필요해 API가 5개가 됨 | 점선 |
| LLM·STT 제공사와 모델명 | 미정. 학교 GCP Vertex AI를 쓸 수 있을 예정이나 모델명은 콘솔에서 확인 후 확정 | 점선, 「제공사 미정」 |
| 프런트 스택 | React + Vite 가정(초안) | 「가정」 표기 |
| 세션 저장소 | 확정: 서버 메모리, 재시작 시 소실 허용 | 실선 |
| 실행 환경 | 확정: 개발은 로컬 Docker, 발표 때만 터널로 HTTPS 주소 공개 (9절) | 실선 |

## 1. 시스템 구성도

```mermaid
flowchart LR
    subgraph FE["프런트엔드 (React + Vite 가정)"]
        UI["화면 1~7"]
        MEDIA["녹음 · 카메라 시선 측정<br/>영상은 서버로 보내지 않음"]
        CLIENT["api/client.ts<br/>VITE_USE_MOCK 전환"]
        MOCK[("shared/mock JSON")]
    end
    subgraph BE["백엔드 FastAPI"]
        API["api/ 라우터 4개"]
        GRAPH["graph/ 준비 그래프 · 평가 그래프"]
        AUDIO["audio/ 받은 녹음 → STT → 파일 삭제"]
        VAL["validators/ 질문·인용 코드 검증"]
        BANK[("banks/ 질문 은행 JSON")]
        STORE[("세션 저장소<br/>서버 메모리 InterviewState")]
    end
    subgraph EXT["외부 서비스 (제공사·모델 미정)"]
        LLM["LLM<br/>학교 GCP Vertex AI 예정"]
        STT["STT 파일 변환"]
        TTS["서버 TTS"]
    end
    BTTS["브라우저 TTS"]

    UI --> CLIENT
    CLIENT -->|"VITE_USE_MOCK=true"| MOCK
    CLIENT -->|"REST 2초 폴링"| API
    MEDIA --> CLIENT
    API --> STORE
    API --> GRAPH
    API --> AUDIO
    GRAPH --> STORE
    GRAPH --> BANK
    GRAPH --> VAL
    GRAPH --> LLM
    AUDIO --> STT
    UI -.->|"미정: 질문 음성"| BTTS
    UI -.->|"미정: 5번째 API 필요"| TTS
```

- 프런트는 화면 5에서 질문 텍스트 표시와 음성 재생, 5초 대기, 녹음, 1분 30초 타이머, 시선 측정(정면 유지 비율·이탈 횟수)을 맡는다.
- 백엔드는 API 4개, State 관리, 그래프 실행, 녹음 수신→STT→삭제를 맡는다.
- 브라우저 TTS와 서버 TTS 둘 다 점선이다. 결정 전에는 프런트가 질문 텍스트를 항상 화면에 보여 TTS가 실패해도 진행할 수 있다(화면 5 예외).

## 2. 준비 파이프라인 (READY까지)

POST /api/interviews 이후 백그라운드로 실행. steps 6개가 화면 3의 진행 표시가 된다. 담당: A(분석), B(질문), C(그래프 연결).

```mermaid
flowchart TD
    IN["서류 4종 텍스트 추출 (코드, A)"] --> P1
    P1["read_posting 공고·직무기술서 분석 (LLM)<br/>요구사항 RQ, 인재상 TALENT"] --> P2
    P2["read_resume 이력서·자소서 분석 (LLM)<br/>주장 Claim"] --> ID
    ID["ID 발급 · 원문 포함 검사 (코드)<br/>RQ-, CL-, CP-"] --> P3
    P3["link 요구사항과 경험 연결 (LLM)<br/>RequirementLink"] --> P4
    P4["checkpoints 검증 포인트 찾기 (LLM)<br/>Checkpoint"] --> P5
    P5["questions 질문 준비 (LLM)<br/>자기소개 1 · 인성 2 · 기술 2"] --> P6
    P6["review 질문 검수 (코드 검증)<br/>ID 존재 · 고정 순서 · 은행 ID"] --> READY
    BANK[("질문 은행 JSON<br/>기술·인성 각 10개")] --> P5
    READY["status = READY"]
    P6 -.->|"실패 시 1회 재시도, 이후 fallback"| P5
```

## 3. 평가 파이프라인 (COMPLETED까지)

마지막 답변과 STT 변환이 모두 끝난 뒤 시작(C↔E 조율 항목). steps 5개가 화면 6의 진행 표시.

```mermaid
flowchart TD
    S0["마지막(Q-5) 답변 수신 → status = EVALUATING"] --> T
    T["transcribe 모든 답변 변환 완료 대기 (STT 백그라운드)"] --> CALC
    CALC["코드 계산: 답변 시간 · 분당 단어 수 · 군말 횟수 · 시선 집계 · 초과 횟수"] --> A1
    A1["attitude 태도 (LLM 조언 문장 생성)"] --> A2
    A2["job_fit 직무 적합성 (LLM 관찰·판정 후보)"] --> A3
    A3["consistency 답변 일관성 (LLM 관찰·판정 후보)"] --> QV
    QV["코드 검증: 인용이 답변 원문에 있는지 · 위치(start, end) 재계산 · QT- 발급 · 없는 인용 제거 · 판정 집계"] --> C
    C["compose 피드백 정리 (코드가 Report 조립)"] --> DONE
    DONE["status = COMPLETED"]
```

## 4. 시퀀스: 준비에서 리포트까지

```mermaid
sequenceDiagram
    participant U as 사용자·프런트
    participant API as FastAPI
    participant G as 그래프
    participant L as LLM
    participant S as STT
    U->>API: POST /api/interviews (서류 4종, 동의)
    API-->>U: 201 session_id, PREPARING
    API->>G: 백그라운드 준비 그래프
    G->>L: 분석·연결·질문 생성 (구조화 출력)
    loop 2초 간격
        U->>API: GET /api/interviews/id
        API-->>U: status, steps (READY면 질문 5개)
    end
    loop 질문 Q-1 ~ Q-5
        U->>API: POST /answers (audio, duration_sec, timed_out, delivery_metrics)
        API-->>U: 202 received, next_question_id
        API->>S: 백그라운드 STT
    end
    API->>G: 평가 그래프 (변환 완료 후)
    G->>L: 태도 조언·직무 적합성·일관성
    loop 2초 간격
        U->>API: GET /api/interviews/id (EVALUATING)
        API-->>U: steps
    end
    U->>API: GET /api/interviews/id/report
    API-->>U: 200 report (COMPLETED)
```

## 5. 면접 중 한 질문의 녹음 → 업로드 → 백그라운드 STT → 삭제

프런트 화면 5의 질문 한 개 흐름과 백엔드 audio/ 흐름. 화면은 업로드 응답(202)을 받으면 STT를 기다리지 않고 다음 질문으로 넘어간다. 실시간 자막은 없다(확정).

```mermaid
sequenceDiagram
    participant FE as 프런트 화면 5
    participant API as POST /answers
    participant AU as audio/
    participant STT as STT 서비스
    participant ST as State.answers
    FE->>FE: 질문 읽기 → 5초 대기 → 녹음 (최대 1분 30초)
    FE->>FE: 답변 완료 또는 시간 초과(timed_out)
    FE->>API: question_id, audio(webm), duration_sec, timed_out, delivery_metrics
    API->>ST: Answer 저장 (transcript_status = PENDING)
    API-->>FE: 202 next_question_id, status
    FE->>FE: 다음 질문 1단계로 (마지막이면 화면 6)
    API->>AU: 백그라운드 변환 요청
    AU->>STT: 음성 파일 변환 (답변 종료 후 파일 방식)
    alt 변환 성공
        STT-->>AU: transcript
        AU->>ST: transcript, DONE, 분당 단어 수·군말 횟수(코드)
    else 무음
        AU->>ST: NO_SPEECH
    else 실패 또는 audio 없음
        AU->>ST: FAILED
    end
    AU->>AU: 음성 파일 삭제 (성공·실패 모두)
```

- 영상은 서버로 보내지 않는다. 시선 측정값만 `delivery_metrics`로 전송(점수 미반영).
- Live 스트리밍은 하지 않는다(확정). 새로고침하면 세션을 버린다(확정).
- 삭제 시점은 「변환 후」(확정)이며, 실패 시 파일을 남길지는 Docs에 명시가 없다(확인 필요).

## 6. 책임 경계 표

| 구성요소 | 하는 일 | 하지 않는 일 |
|---|---|---|
| LLM | 서류에서 요구사항·주장·검증 포인트 관찰, 요구사항과 경험 연결, 질문 문장 생성, 판정 후보와 이유·조언 문장 생성 (모두 Pydantic 구조화 출력) | ID 발급, 시간·횟수·비율 계산, 인용 위치 계산, 인용 존재 검증, 판정 집계, 면접 중 질문 변경 |
| 코드(노드·validators) | ID 발급, LLM이 참조한 ID의 존재 검사, Claim 원문 포함 검사, 질문 5개 고정 순서·은행 ID 검증, 답변 시간·분당 단어 수·군말 횟수·시선 집계, 인용 원문 검사와 `start`/`end` 계산, 판정 집계, Report 조립, LLM 실패 시 1회 재시도 후 fallback | 서류 내용 해석, 문장 생성 |
| 프런트 | 화면 1~7, 질문 표시·음성 재생, 5초 대기, 녹음·타이머, 카메라 시선 측정, 업로드, 2초 폴링, 열거값→화면 문구 변환 | 점수·판정 계산, 영상 서버 전송, 면접 중 피드백 표시 |
| FastAPI / audio | API 4개, 백그라운드 작업 시작, 녹음 수신→STT→삭제, 세션 State 저장(메모리) | 질문 기대 요소·평가 기준을 면접 중 응답에 포함, 음성 파일 장기 보관 |
| STT | 음성 파일을 텍스트로 변환 | 분석·평가 |
| 세션 저장소 | InterviewState 보관(서버 재시작 시 소실 허용) | 영구 저장, 이어하기 |

원칙 요약: LLM은 관찰·생성, 코드는 계산·검증. 코드로 계산할 수 있는 것은 LLM에게 시키지 않고, 답변 텍스트에 없는 문장은 코드가 인용에서 버린다.

## 7. 담당별 위치

| 담당 | 백엔드 | 화면 |
|---|---|---|
| A 서류 입력·분석 | nodes/prep (분석) | 1, 2 |
| B 질문 준비·로딩 | nodes/prep (질문), banks, validators (질문·인용) | 3, 6 (단계 진행 컴포넌트) |
| C 세션·통합 | schemas, graph, api, audio | (없음) |
| D 면접 화면·전체 UI | (프런트 시선 계산) | 프런트 뼈대, api/client.ts, 4, 5 |
| E 피드백 | nodes/evaluate (인용 검증 함수는 B의 validators를 호출) | 7 |

## 8. 확인 필요

1. TTS 방식(브라우저 vs 서버)에 따라 API 개수와 프런트·백엔드 경계가 달라진다. 킥오프 결정 필요.
2. LLM·STT 제공사, 모델, 호출 한도 미정. 그래프의 노드별 모델 분리 여부도 미정.
3. 준비 파이프라인의 6개 단계(steps)와 그래프 노드의 대응, 「ID 발급」이 어느 step에 속하는지는 Docs에 명시가 없다. 위 그림은 ID 표(A가 만든다)를 근거로 배치한 추정이다.
4. 평가 파이프라인 내부 순서(attitude → job_fit → consistency)는 steps 순서에서 읽은 것이며 병렬 실행 여부는 정해지지 않았다.
5. 변환 실패 시 음성 파일 삭제 여부, 그리고 재시도·타임아웃 정책은 미정.
6. 프런트 스택(React + Vite)은 가정이다.

## 9. 실행 환경 (Docker)

개발은 로컬 Docker(`docker compose`)로, 발표 때만 터널로 HTTPS 주소를 임시 공개한다. (확정) 브라우저는 `localhost` 또는 HTTPS에서만 마이크·카메라를 허용하므로, 로컬 개발에는 HTTPS가 필요 없고 발표 때만 터널이 필요하다.

```mermaid
flowchart LR
    B["브라우저"] -->|"localhost 또는 터널 HTTPS"| FE["frontend 컨테이너<br/>정적 파일 + /api 프록시"]
    FE -->|"/api"| BE["backend 컨테이너<br/>FastAPI, 워커 1개"]
    BE --> LLM["외부 LLM·STT"]
    T["터널 (발표 때만)"] -.-> FE
```

| 항목 | 규칙 |
|---|---|
| 접속 주소 | 프런트 컨테이너가 `/api`를 백엔드로 프록시해 주소를 하나로 만든다. 터널은 프런트 포트 하나만 연다. CORS 문제도 줄어든다. (제안) |
| 세션 메모리 | 백엔드 워커는 1개, 컨테이너도 1개로 고정한다. 여러 개면 세션이 서로 보이지 않는다. 컨테이너를 재시작하면 세션이 사라진다(허용). (제안) |
| 음성 임시 파일 | 컨테이너 임시 폴더에 두고 STT 후 삭제한다. 볼륨은 만들지 않는다. (제안) |
| LLM 인증 | 컨테이너 안에는 개인 gcloud 로그인이 없다. 제공사 확정 후 키나 서비스 계정 키 파일을 런타임에 주입하고, 이미지와 저장소에는 넣지 않는다. (미정) |
| 프런트 환경변수 | `VITE_*`는 빌드 시점 값이라 바꾸면 프런트 이미지를 다시 빌드해야 한다. ([docs/07-dev-rules.md](07-dev-rules.md) 7절) |
| 터널 | 발표 전 리허설에서 터널 주소로 마이크·카메라가 허용되는지 확인한다. 주소는 실행마다 바뀔 수 있다. (제안) |
