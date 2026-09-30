import type { NormalizedLandmark } from "@mediapipe/tasks-vision";
import type { PerceptionConfig } from "./config";
import { DEFAULT_PERCEPTION_CONFIG } from "./config";
import type { GazeBaseline } from "./types";

export interface GazeFeatures {
  left_iris_ratio: number;
  right_iris_ratio: number;
  nose_x: number;
}

const LEFT_IRIS = [468, 469, 470, 471, 472];
const RIGHT_IRIS = [473, 474, 475, 476, 477];

const mean = (values: number[]) => values.reduce((sum, value) => sum + value, 0) / values.length;

function irisCenterX(landmarks: NormalizedLandmark[], indices: number[]): number {
  return mean(indices.map((index) => landmarks[index].x));
}

function normalizedRatio(value: number, a: number, b: number): number {
  const width = Math.abs(b - a);
  return width > 0 ? (value - Math.min(a, b)) / width : 0.5;
}

/** 홍채 위치와 머리 중심을 캘리브레이션 기준과 비교합니다. */
export class IrisGazeAnalyzer {
  constructor(private readonly config: PerceptionConfig = DEFAULT_PERCEPTION_CONFIG) {}

  calibrate(samples: GazeFeatures[]): GazeBaseline {
    if (samples.length < 5) throw new Error("시선 캘리브레이션 표본이 부족합니다.");
    return {
      left_iris_ratio: mean(samples.map((sample) => sample.left_iris_ratio)),
      right_iris_ratio: mean(samples.map((sample) => sample.right_iris_ratio)),
      nose_x: mean(samples.map((sample) => sample.nose_x)),
    };
  }

  extract(landmarks: NormalizedLandmark[]): GazeFeatures {
    if (landmarks.length < 478) throw new Error("홍채 landmark가 포함되지 않았습니다.");
    const leftIrisX = irisCenterX(landmarks, LEFT_IRIS);
    const rightIrisX = irisCenterX(landmarks, RIGHT_IRIS);
    return {
      left_iris_ratio: normalizedRatio(leftIrisX, landmarks[33].x, landmarks[133].x),
      right_iris_ratio: normalizedRatio(rightIrisX, landmarks[362].x, landmarks[263].x),
      nose_x: landmarks[1].x,
    };
  }

  isLookingAtCamera(features: GazeFeatures, baseline: GazeBaseline): boolean {
    return (
      Math.abs(features.left_iris_ratio - baseline.left_iris_ratio) < this.config.gaze_horizontal_threshold &&
      Math.abs(features.right_iris_ratio - baseline.right_iris_ratio) < this.config.gaze_horizontal_threshold &&
      Math.abs(features.nose_x - baseline.nose_x) < this.config.head_position_threshold
    );
  }
}
