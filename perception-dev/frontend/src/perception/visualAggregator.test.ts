import { describe, expect, it } from "vitest";
import { DEFAULT_PERCEPTION_CONFIG } from "./config";
import { AnswerVisualAggregator } from "./visualAggregator";

describe("AnswerVisualAggregator", () => {
  it("답변 프레임을 비율로 집계한다", () => {
    const aggregator = new AnswerVisualAggregator(DEFAULT_PERCEPTION_CONFIG);
    aggregator.add({
      face_detected: true,
      looking_at_camera: true,
      blendshapes: { mouthSmileLeft: 0.1 },
    });
    aggregator.add({
      face_detected: true,
      looking_at_camera: false,
      blendshapes: { mouthSmileLeft: 0.5 },
    });
    aggregator.add({ face_detected: false });

    expect(aggregator.finalize()).toMatchObject({
      face_detection_ratio: 2 / 3,
      camera_gaze_ratio: 1 / 2,
    });
  });

  it("얼굴 검출률이 기준보다 낮으면 null을 반환한다", () => {
    const aggregator = new AnswerVisualAggregator(DEFAULT_PERCEPTION_CONFIG);
    aggregator.add({ face_detected: true });
    aggregator.add({ face_detected: false });

    expect(aggregator.finalize()).toBeNull();
  });
});
