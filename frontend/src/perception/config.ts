export interface PerceptionConfig {
  sample_interval_ms: number;
  minimum_face_detection_ratio: number;
  gaze_horizontal_threshold: number;
  head_position_threshold: number;
  gaze_away_min_ms: number;
}

export const DEFAULT_PERCEPTION_CONFIG: PerceptionConfig = {
  sample_interval_ms: 100,
  minimum_face_detection_ratio: 0.6,
  gaze_horizontal_threshold: 0.12,
  head_position_threshold: 0.08,
  gaze_away_min_ms: 1_000,
};
