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
