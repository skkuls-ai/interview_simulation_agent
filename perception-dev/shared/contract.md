# PerceptionResult Contract v1.0

`PerceptionResult`는 시각·음성 분석 영역과 LangGraph 영역 사이의 유일한 데이터 계약입니다.

```json
{
  "schema_version": "1.0",
  "session_id": "session_001",
  "question_id": "question_001",
  "answer_id": "answer_001",
  "transcript": {
    "text": "RAG 프로젝트에서 검색 파이프라인을 담당했습니다.",
    "duration_seconds": 24.5
  },
  "audio": {
    "eojeol_count": 6,
    "speech_rate": 14.7
  },
  "visual": {
    "face_detection_ratio": 0.95,
    "camera_gaze_ratio": 0.78,
    "expression_variance": 0.14
  },
  "quality": {
    "audio_available": true,
    "visual_available": true
  },
  "warnings": []
}
```

## 의미

- `duration_seconds`: 녹음 시작부터 답변 완료까지의 실제 경과 시간
- `eojeol_count`: transcript를 공백 기준으로 나눈 어절 수
- `speech_rate`: `eojeol_count / (duration_seconds / 60)`
- `face_detection_ratio`: 전체 분석 프레임 중 얼굴이 검출된 비율
- `camera_gaze_ratio`: 얼굴 검출 프레임 중 카메라 방향으로 판정된 비율
- `expression_variance`: 입 벌림을 제외한 선택 blendshape들의 시간축 분산 평균

시각 분석이 불가능하면 `visual`은 `null`이고 `visual_available`은 `false`입니다.
