import type { BlendshapeScores } from "./expressionAnalyzer";
import type { VisualMetrics } from "./types";
import type { PerceptionConfig } from "./config";
import { DEFAULT_PERCEPTION_CONFIG } from "./config";
import { TRACKED_BLENDSHAPES } from "./expressionAnalyzer";

export interface VisualFrameSample {
  face_detected: boolean;
  looking_at_camera?: boolean;
  blendshapes?: BlendshapeScores;
}

/** 답변 구간의 프레임별 결과를 최종 VisualMetrics로 집계할 구현 지점입니다. */
export interface VisualAggregator {
  reset(): void;
  add(sample: VisualFrameSample): void;
  finalize(): VisualMetrics | null;
}

const mean = (values: number[]) => values.length
  ? values.reduce((sum, value) => sum + value, 0) / values.length
  : 0;

function variance(values: number[]): number {
  if (!values.length) return 0;
  const average = mean(values);
  return mean(values.map((value) => (value - average) ** 2));
}

export class AnswerVisualAggregator implements VisualAggregator {
  private totalFrames = 0;
  private detectedFrames = 0;
  private forwardFrames = 0;
  private expressionSamples: BlendshapeScores[] = [];

  constructor(private readonly config: PerceptionConfig = DEFAULT_PERCEPTION_CONFIG) {}

  reset(): void {
    this.totalFrames = 0;
    this.detectedFrames = 0;
    this.forwardFrames = 0;
    this.expressionSamples = [];
  }

  add(sample: VisualFrameSample): void {
    this.totalFrames += 1;
    if (!sample.face_detected) return;
    this.detectedFrames += 1;
    if (sample.looking_at_camera) this.forwardFrames += 1;
    if (sample.blendshapes) this.expressionSamples.push(sample.blendshapes);
  }

  finalize(): VisualMetrics | null {
    if (!this.totalFrames) return null;
    const faceDetectionRatio = this.detectedFrames / this.totalFrames;
    if (!this.detectedFrames || faceDetectionRatio < this.config.minimum_face_detection_ratio) return null;

    const expressionVariance = mean(
      TRACKED_BLENDSHAPES.map((name) =>
        variance(this.expressionSamples.map((sample) => sample[name] ?? 0)),
      ),
    );

    return {
      face_detection_ratio: faceDetectionRatio,
      camera_gaze_ratio: this.forwardFrames / this.detectedFrames,
      expression_variance: expressionVariance,
    };
  }
}
