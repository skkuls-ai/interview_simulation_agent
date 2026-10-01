# Frontend

면접 시뮬레이션 웹 UI입니다 (React, Vite, TypeScript). 백엔드 API 4개와 연결돼 서류 업로드부터 피드백까지 화면 1→7을 진행합니다.

## 실행

```bash
npm ci
VITE_USE_MOCK=false npm run dev      # 서버 연결 모드 (백엔드를 8000에서 먼저 실행)
npm run dev                          # mock 모드 (백엔드 없이 화면 흐름만 확인)
```

기본 주소는 `http://localhost:5173`이고, 개발 서버가 `/api`를 `http://localhost:8000`으로 프록시합니다. 빌드와 타입 검사는 `npm run build`입니다. `VITE_USE_MOCK`은 시작·빌드 시점에 고정되고, 로컬 기본값은 mock(`true`), Docker 빌드 기본값은 서버 연결(`false`)입니다.

## 구조

| 위치 | 역할 |
|---|---|
| `src/app/App.tsx` | 화면 단계 상태와 서버 연결 (세션 생성, 질문·리포트 보관, 답변 제출) |
| `src/pages/` | 화면 1~7 (`StartScreen`, `SetupScreen`, `AnalysisScreen`, `DeviceCheckScreen`, `InterviewScreen`, `InterviewEndScreen`, `EvaluationScreen`, `ResultScreen`) |
| `src/api/` | `client.ts`(요청·오류), `interview.ts`(API 4개), `useSessionStatus.ts`(2초 폴링), `reportAdapter.ts`(서버 리포트 → 결과 화면 모양) |
| `src/perception/` | 카메라 시선 측정 (브라우저 안에서 계산, 영상은 서버로 보내지 않음) |
| `src/recording/` | 답변 녹음 |
| `src/mocks/`, `src/types/` | mock 데이터, 화면용 타입 |

mock 모드에서는 화면 3·6이 타이머로 진행되고 질문·리포트가 `src/mocks/interview.ts`의 값입니다. 서버 연결 모드에서는 서버의 진행 단계, 질문, 리포트를 씁니다. 세션이 사라지면(서버 재시작) 로딩 화면에 안내와 「처음으로」가 나옵니다.
