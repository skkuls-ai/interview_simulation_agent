# Frontend

면접 시뮬레이션 웹 UI의 React 기본 구조입니다. 현재는 디자인 시스템과 실제 API를 연결하기 전 단계로, 목 데이터를 이용해 전체 화면 흐름을 확인할 수 있습니다.

## 실행

```bash
npm install
npm run dev
```

기본 주소는 `http://localhost:5173`입니다.

## 현재 화면 흐름

```text
준비 및 선택 문서 업로드
→ 분석 진행
→ 카메라·마이크 점검
→ 자기소개/본 질문/꼬리질문/마무리 질문
→ 평가 대기
→ 종합 결과
```

`src/services/api`는 백엔드 API 연결 지점이고, `src/mocks`는 실제 연동 전에 사용하는 개발 데이터입니다. 백엔드의 `prompt.type` 계약이 확정되면 `src/types/interview.ts`와 API 응답 어댑터를 맞춰야 합니다.
