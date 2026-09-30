export interface GazeBaseline {
  left_iris_ratio: number;
  right_iris_ratio: number;
  nose_x: number;
}

/** 답변 제출 API에 포함되는 비언어 참고 지표입니다. */
export interface DeliveryMetrics {
  measurable: boolean;
  frontal_ratio: number | null;
  gaze_away_count: number | null;
}
