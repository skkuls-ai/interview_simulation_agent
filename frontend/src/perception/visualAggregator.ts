import type { PerceptionConfig } from "./config";
import { DEFAULT_PERCEPTION_CONFIG } from "./config";
import type { DeliveryMetrics } from "./types";

export interface VisualFrameSample {
  face_detected: boolean;
  looking_at_camera?: boolean;
}

/** 프레임별 판정을 답변 하나의 시선 지표로 집계합니다. */
export class AnswerVisualAggregator {
  private totalFrames = 0;
  private detectedFrames = 0;
  private forwardFrames = 0;
  private gazeAwayCount = 0;
  private previousLookingAtCamera: boolean | null = null;

  constructor(private readonly config: PerceptionConfig = DEFAULT_PERCEPTION_CONFIG) {}

  reset(): void {
    this.totalFrames = 0;
    this.detectedFrames = 0;
    this.forwardFrames = 0;
    this.gazeAwayCount = 0;
    this.previousLookingAtCamera = null;
  }

  add(sample: VisualFrameSample): void {
    this.totalFrames += 1;
    if (!sample.face_detected) return;
    this.detectedFrames += 1;
    const lookingAtCamera = sample.looking_at_camera === true;
    if (lookingAtCamera) this.forwardFrames += 1;
    if (!lookingAtCamera && this.previousLookingAtCamera !== false) this.gazeAwayCount += 1;
    this.previousLookingAtCamera = lookingAtCamera;
  }

  finalize(): DeliveryMetrics {
    if (!this.totalFrames) return this.unmeasurable();
    const faceDetectionRatio = this.detectedFrames / this.totalFrames;
    if (!this.detectedFrames || faceDetectionRatio < this.config.minimum_face_detection_ratio) {
      return this.unmeasurable();
    }
    return {
      measurable: true,
      frontal_ratio: this.forwardFrames / this.detectedFrames,
      gaze_away_count: this.gazeAwayCount,
    };
  }

  private unmeasurable(): DeliveryMetrics {
    return { measurable: false, frontal_ratio: null, gaze_away_count: null };
  }
}
