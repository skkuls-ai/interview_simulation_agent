# 면까몰 (ProofInterview) — 서류 기반 AI 모의 면접

**내 지원서류를 파고드는 면접관, 근거로 설명하는 평가.**
이력서·채용공고·직무기술서·자기소개서 4종을 넣으면 질문 5개짜리 음성 모의 면접을 진행하고, 답변 인용을 근거로 한 피드백(태도·직무 적합성·답변 일관성)을 보여 주는 웹 서비스입니다. AI Agent 전문가 양성과정 미니 팀 프로젝트(2026.9.28~10.2)의 1차 MVP입니다.

## 화면 흐름

1. 시작 → 2. 서류 업로드(파일 또는 텍스트, 개인정보 동의) → 3. AI 분석 로딩(서버 진행 단계 표시)
4. 면접대기실(마이크·카메라 확인) → 5. 면접(질문 음성 → 5초 → 녹음, 최대 1분 30초) → 6. 평가 로딩 → 7. 면접 피드백

## 구성

| 영역 | 기술 | 위치 |
|---|---|---|
| 프런트 | React, Vite, TypeScript (카메라 시선 측정은 브라우저에서 계산) | `frontend/` |
| 백엔드 | FastAPI, API 4개, 메모리 세션 (워커 1개 고정) | `backend/app/` |
| LLM·STT | Gemini (기본 `gemini-3.8-flash`), 음성 변환도 Gemini | `backend/app/llm/`, `backend/app/audio/` |
| 서류 분석·질문 생성·평가 | 준비 그래프 / 평가 그래프 | `backend/app/graph/`, `backend/app/nodes/` |
| 인용·질문 검증 | 코드 검증 | `backend/app/validators/` |
| 고정 데모 데이터 | 지원자A 서류 4종, mock 응답 | `shared/mock/` |

원칙: LLM은 생성과 관찰을, 코드는 연결·인용·형식 검증을 맡습니다. 음성 파일은 변환 후 삭제하고, 영상은 서버로 보내지 않으며, 카메라 지표는 판정에 쓰지 않습니다.

## 실행 준비

Python 3.12, Node 22(또는 Docker)가 필요합니다.

```bash
cp .env.example .env
```

`.env`에 Gemini 연결 정보를 넣습니다. **키는 절대 커밋하지 마세요** (`.env*`는 `.gitignore`에 있습니다).

| 방식 | `.env`에 넣을 것 |
|---|---|
| Vertex AI + gcloud 로그인 (권장) | `GOOGLE_CLOUD_PROJECT=프로젝트ID`, `GOOGLE_CLOUD_LOCATION=global`, 인증: `gcloud auth application-default login` |
| Vertex AI API 키 | `GOOGLE_GENAI_USE_VERTEXAI=true`, `GEMINI_API_KEY=키` |
| Gemini API(AI Studio 키) | `GEMINI_API_KEY=키` (`GOOGLE_GENAI_USE_VERTEXAI`는 넣지 않음) |

키가 없으면 서버는 **가짜 진행기**(`shared/mock`을 재생)로 동작하고 STT도 고정 텍스트를 돌려줍니다. 화면 흐름만 확인할 때 쓸 수 있습니다.

## 실행 방법

### A. Docker (프런트 + 백엔드 한 번에)

```bash
docker compose up --build
```

http://localhost:8080 으로 접속합니다. 프런트 컨테이너가 `/api`를 백엔드(8000)로 프록시합니다. `VITE_USE_MOCK`은 **빌드 시점**에 고정되므로 값을 바꾸면 `docker compose build frontend`를 다시 실행하세요. 컨테이너 안에는 개인 gcloud 로그인이 없으니, Vertex 로그인 방식 대신 API 키 방식을 쓰세요.

### B. 로컬 개발

```bash
# 백엔드 (터미널 1)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000        # 세션이 메모리에 있으므로 워커 1개, --reload 없이 권장

# 프런트 (터미널 2)
cd frontend
npm ci
VITE_USE_MOCK=false npm run dev         # http://localhost:5173, /api는 8000으로 프록시
```

마이크·카메라는 `localhost` 또는 HTTPS에서만 허용됩니다. Chrome을 권장합니다.

## 환경변수

| 변수 | 값 | 설명 |
|---|---|---|
| `INTERVIEW_GRAPH_MODE` | `auto`(기본) / `real` / `fake` | `auto`는 키가 있으면 진짜 그래프, 없으면 가짜 진행기 |
| `STT_MODE` | `auto`(기본) / `gemini` / `stub` | `auto`는 키가 있으면 Gemini 변환, 없으면 고정 텍스트 |
| `STT_MODEL` | 기본 `gemini-3.8-flash` | 음성 변환 모델 |
| `GEMINI_MODEL` | 기본 `gemini-3.8-flash` | 기본 모델 |
| `INTERVIEW_MODEL_<역할>`, `INTERVIEW_THINKING_<역할>` | `EVALUATOR`, `COACH`, `VALIDATOR` 등 / `LOW`·`MEDIUM`·`HIGH` | 역할별 모델과 추론 수준 |
| `VITE_USE_MOCK` | `true`/`false` | 프런트가 mock 데이터를 쓸지(빌드·개발 서버 시작 시 고정). 로컬 기본값은 mock, Docker 기본값은 서버 연결 |

## 데모 데이터

- 고정 데모 서류(지원자A): `shared/mock/sample_inputs.json` — 4칸에 그대로 붙여 넣으면 됩니다.
- 면접 질문 5개는 서류를 분석한 뒤 만들어집니다: Q-1 자기소개(고정 문구), Q-2·Q-3 인성(질문 은행에서 서류에 맞게 선택), Q-4·Q-5 기술(LLM 생성 후 코드 검증). 가짜 진행기(키 없음)에서는 `shared/mock/session_ready.json`의 고정 질문을 씁니다.
- 인성 질문 은행: `backend/app/banks/` (잡다에서 제공하는 「역량기반 구조화 면접 질문 150선」, 출처는 `backend/app/banks/README.md`).

## 테스트

```bash
cd backend && pytest                 # 백엔드 자동 테스트 (실제 LLM 호출 없음)
cd frontend && npm run build         # 타입 검사 + 빌드
```

## 알려진 제약

- 세션은 서버 메모리에만 있어 **서버를 재시작하면 진행 중인 면접이 사라집니다**(화면은 「처음으로」 안내). 새로고침 후 이어하기와 로그인은 1차 범위 밖입니다.
- 같은 입력이라도 LLM 판정은 실행마다 조금씩 달라질 수 있습니다. 모든 판정은 실제 답변 인용과 이유를 함께 보여 주고, 인용은 코드가 원문에서 다시 찾아 검증합니다.
- 호출 한도가 낮은 무료 키로는 반복 실행 중 한도에 걸릴 수 있습니다.

## 문서

기획·화면·기능·API·아키텍처·일정·개발 규칙·테스트 시나리오는 [`docs/`](docs/)에 있습니다.
