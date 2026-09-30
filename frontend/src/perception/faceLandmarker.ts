import { FaceLandmarker, FilesetResolver, type FaceLandmarkerResult } from "@mediapipe/tasks-vision";

export interface FaceLandmarkerAdapter {
  initialize(): Promise<void>;
  detect(video: HTMLVideoElement, timestampMs: number): FaceLandmarkerResult;
  dispose(): void;
}

export class MediaPipeFaceLandmarkerAdapter implements FaceLandmarkerAdapter {
  private landmarker: FaceLandmarker | null = null;

  async initialize(): Promise<void> {
    const vision = await FilesetResolver.forVisionTasks("/mediapipe/wasm");
    this.landmarker = await FaceLandmarker.createFromOptions(vision, {
      baseOptions: { modelAssetPath: "/models/face_landmarker.task", delegate: "GPU" },
      runningMode: "VIDEO",
      numFaces: 1,
      minFaceDetectionConfidence: 0.5,
      minFacePresenceConfidence: 0.5,
      minTrackingConfidence: 0.5,
      outputFaceBlendshapes: false,
      outputFacialTransformationMatrixes: false,
    });
  }

  detect(video: HTMLVideoElement, timestampMs: number): FaceLandmarkerResult {
    if (!this.landmarker) throw new Error("Face Landmarker가 초기화되지 않았습니다.");
    return this.landmarker.detectForVideo(video, timestampMs);
  }

  dispose(): void {
    this.landmarker?.close();
    this.landmarker = null;
  }
}
