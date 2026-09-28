export interface GazeBaseline {
  left_iris_ratio: number;
  right_iris_ratio: number;
  nose_x: number;
}

export interface VisualMetrics {
  face_detection_ratio: number;
  camera_gaze_ratio: number;
  expression_variance: number;
}

export interface PerceptionResult {
  schema_version: "1.0";
  session_id: string;
  question_id: string;
  answer_id: string;
  transcript: {
    text: string;
    duration_seconds: number;
  };
  audio: {
    eojeol_count: number;
    speech_rate: number;
  };
  visual: VisualMetrics | null;
  quality: {
    audio_available: boolean;
    visual_available: boolean;
  };
  warnings: string[];
}
