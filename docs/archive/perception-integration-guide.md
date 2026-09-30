# 면접 Perception 모듈 연동 가이드

> **보관용 문서 (perception 모듈 기준 초안).** MVP 기준의 API와 시선 지표는 [04-api-schema.md](../04-api-schema.md)를 따른다. 이 문서와 04는 다음 점이 다르며, 통합 여부는 팀 합의 후 정한다.
>
> | 항목 | 04-api-schema.md (MVP 기준) | 이 문서 |
> |---|---|---|
> | 엔드포인트 | `POST /api/interviews/{id}/answers`에 녹음과 측정값을 함께 업로드 | 별도 `POST /api/perception/analyze` |
> | 시각 지표 | `measurable`, `frontal_ratio`, `gaze_away_count` | `face_detection_ratio`, `camera_gaze_ratio`, `expression_variance` |
> | STT | C의 `audio/`가 변환 후 파일 삭제 | perception 모듈이 STT까지 수행 |

## 1. 모듈 역할

사용자의 면접 답변에서 다음 정보를 분석합니다.

- 음성을 텍스트로 변환
- 답변 시간, 어절 수, 분당 어절 수 계산
- 얼굴 검출 비율 계산
- 카메라 방향 유지 비율 계산
- 표정 변화량 계산

감정, 긴장도, 자신감 등은 판단하지 않습니다.

## 2. 처리 흐름

```text
답변 시작
→ 카메라 분석 + 마이크 녹음
→ 답변 종료
→ 오디오와 시각 지표를 백엔드로 전송
→ STT 및 음성 지표 계산
→ PerceptionResult 반환
→ LangGraph 답변 평가 노드에 전달
```

## 3. API 요청

```http
POST /api/perception/analyze
Content-Type: multipart/form-data
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `session_id` | string | 면접 세션 ID |
| `question_id` | string | 현재 질문 ID |
| `answer_id` | string | 현재 답변 ID |
| `duration_seconds` | number | 답변 시작부터 종료까지의 시간 |
| `audio` | file | 브라우저에서 녹음한 오디오 |
| `visual_metrics` | JSON string | 프런트에서 계산한 시각 지표 |

`visual_metrics` 예시:

```json
{
  "face_detection_ratio": 1.0,
  "camera_gaze_ratio": 0.85,
  "expression_variance": 0.002
}
```

카메라 분석이 불가능하면 `visual_metrics`는 생략할 수 있습니다.

## 4. API 응답

```json
{
  "schema_version": "1.0",
  "session_id": "session-001",
  "question_id": "question-001",
  "answer_id": "answer-001",
  "transcript": {
    "text": "프로젝트에서 API 서버 개발을 담당했습니다.",
    "duration_seconds": 20.5
  },
  "audio": {
    "eojeol_count": 6,
    "speech_rate": 17.6
  },
  "visual": {
    "face_detection_ratio": 1.0,
    "camera_gaze_ratio": 0.85,
    "expression_variance": 0.002
  },
  "quality": {
    "audio_available": true,
    "visual_available": true
  },
  "warnings": []
}
```

## 5. 필드 의미와 사용 원칙

- `transcript.text`: STT로 변환된 사용자 답변
- `duration_seconds`: 침묵을 포함한 전체 답변 시간
- `eojeol_count`: 공백 기준 어절 수
- `speech_rate`: 1분당 어절 수
- `face_detection_ratio`: 얼굴이 정상적으로 검출된 프레임 비율
- `camera_gaze_ratio`: 캘리브레이션 기준 카메라 방향 유지 비율
- `expression_variance`: 입 벌림을 제외한 표정 변화량
- `quality`: 음성·시각 분석 결과를 사용할 수 있는지 표시
- `warnings`: `stt_failed`, `visual_unavailable` 등의 분석 오류

`transcript.text`는 답변 내용 평가에 사용합니다. 음성·시각 지표는 점수에 직접 반영하지 않고 참고 피드백으로만 사용합니다.
