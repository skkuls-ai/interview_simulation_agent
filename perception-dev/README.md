# Perception Module

면접 답변의 음성·시선·표정 정보를 분석하고 LangGraph에 전달할 `PerceptionResult`를 생성합니다.
최종 UI는 포함하지 않으며, 프런트엔드에서 재사용할 분석·녹음·API 모듈만 제공합니다.

## 분석 범위

- 음성: Gemini STT, 답변 시간, 어절 수, 분당 어절 수
- 시각: 얼굴 검출 비율, 카메라 방향 유지 비율, 표정 변화량
- 제외: 감정, 긴장도, 자신감, 필러, pitch, energy

Gemini STT 기본 모델은 `gemini-3.8-flash`입니다.

## 구조

```text
perception-dev/
├── backend/
│   ├── app/perception/       # STT, 음성 지표, 결과 통합 API
│   └── tests/
├── frontend/
│   ├── assets/models/        # Face Landmarker 모델
│   └── src/
│       ├── perception/       # MediaPipe 시각 분석
│       ├── recording/        # 브라우저 마이크 녹음
│       └── api/              # Perception API 클라이언트
└── shared/
    ├── contract.md
    └── fixtures/
```

## API 데이터 필드

### 요청 필드

`POST /api/perception/analyze`에 `multipart/form-data`로 전송합니다.

| 필드 | 타입 | 의미 |
|---|---|---|
| `session_id` | string | 질문·답변·평가를 묶는 모의 면접 1회의 ID |
| `question_id` | string | 현재 답변하는 질문의 ID. 대질문과 꼬리질문 모두 동일한 필드를 사용 |
| `answer_id` | string | 답변 시도 1회의 ID. 같은 질문에 다시 답하면 새로운 ID 발급 |
| `duration_seconds` | number | 녹음 시작부터 답변 종료까지의 시간(초). 침묵 구간 포함 |
| `audio` | file | 브라우저에서 녹음한 답변 오디오 |
| `visual_metrics` | JSON string, optional | 브라우저에서 계산한 시각 분석 결과. 카메라 분석이 불가능하면 생략 |

### 응답 필드 (`PerceptionResult`)

| 필드 | 타입 | 의미 |
|---|---|---|
| `schema_version` | string | 데이터 계약 버전. 현재 값은 `1.0` |
| `session_id` | string | 요청에서 전달된 면접 세션 ID |
| `question_id` | string | 요청에서 전달된 현재 질문 ID |
| `answer_id` | string | 요청에서 전달된 답변 ID |
| `transcript.text` | string | Gemini STT로 변환한 사용자 답변 |
| `transcript.duration_seconds` | number | 침묵을 포함한 전체 답변 시간(초) |
| `audio.eojeol_count` | integer | transcript를 공백 기준으로 나눈 어절 수 |
| `audio.speech_rate` | number | 분당 어절 수. `eojeol_count / duration_seconds × 60` |
| `visual.face_detection_ratio` | number | 전체 분석 프레임 중 얼굴이 검출된 비율(0~1) |
| `visual.camera_gaze_ratio` | number | 얼굴 검출 프레임 중 캘리브레이션 기준 카메라 방향을 유지한 비율(0~1) |
| `visual.expression_variance` | number | 입 벌림을 제외한 얼굴 blendshape의 시간축 변화량 |
| `quality.audio_available` | boolean | STT 결과를 답변 분석에 사용할 수 있는지 여부 |
| `quality.visual_available` | boolean | 시각 분석 결과를 사용할 수 있는지 여부 |
| `warnings` | string[] | 품질 저하 원인. 현재 `stt_failed`, `visual_unavailable` 사용 |

`visual`은 카메라 미사용 또는 얼굴 검출 품질 부족 시 `null`입니다.
음성·시각 지표는 합격 점수가 아니라 전달 방식 피드백을 위한 참고값으로 사용합니다.

## 백엔드 연결

```python
from app.perception.routes import router as perception_router

app.include_router(perception_router)
```

환경변수는 `.env.example`을 참고해 설정합니다.

```dotenv
GEMINI_API_KEY=your_gemini_api_key_here
```

## 프런트엔드 연결

```ts
import { PerceptionApiClient } from "./api";
import { BrowserPerceptionController } from "./perception";
import { BrowserAnswerRecorder } from "./recording";

const perception = new BrowserPerceptionController();
const recorder = new BrowserAnswerRecorder();
const api = new PerceptionApiClient();
```

MediaPipe 실행 시 다음 파일을 최종 프런트엔드의 `public` 디렉터리에 배치해야 합니다.

```text
frontend/assets/models/face_landmarker.task
  → public/models/face_landmarker.task

node_modules/@mediapipe/tasks-vision/wasm/
  → public/mediapipe/wasm/
```

## 검증

```bash
PYTHONPATH=perception-dev/backend python -m pytest perception-dev/backend/tests
npm --prefix perception-dev/frontend install
npm --prefix perception-dev/frontend run build
npm --prefix perception-dev/frontend run test
```

Agent 연동 데이터 형식은 `shared/contract.md`를 기준으로 합니다.
