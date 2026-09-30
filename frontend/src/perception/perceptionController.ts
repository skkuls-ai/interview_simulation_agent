import type { FaceLandmarkerResult } from "@mediapipe/tasks-vision";
import type { PerceptionConfig } from "./config";
import { DEFAULT_PERCEPTION_CONFIG } from "./config";
import { MediaPipeFaceLandmarkerAdapter, type FaceLandmarkerAdapter } from "./faceLandmarker";
import { IrisGazeAnalyzer, type GazeFeatures } from "./gazeAnalyzer";
import type { DeliveryMetrics, GazeBaseline } from "./types";
import { AnswerVisualAggregator } from "./visualAggregator";

export class BrowserPerceptionController {
  private video: HTMLVideoElement | null = null;
  private baseline: GazeBaseline | null = null;
  private running = false;
  private hasActiveAnswer = false;
  private animationFrame: number | null = null;
  private lastSampleAt = 0;
  private readonly gazeAnalyzer: IrisGazeAnalyzer;
  private readonly aggregator: AnswerVisualAggregator;

  constructor(
    private readonly config: PerceptionConfig = DEFAULT_PERCEPTION_CONFIG,
    private readonly landmarker: FaceLandmarkerAdapter = new MediaPipeFaceLandmarkerAdapter(),
  ) {
    this.gazeAnalyzer = new IrisGazeAnalyzer(config);
    this.aggregator = new AnswerVisualAggregator(config);
  }

  async initialize(video: HTMLVideoElement): Promise<void> {
    this.video = video;
    await this.landmarker.initialize();
  }

  async calibrate(): Promise<GazeBaseline> {
    if (!this.video) throw new Error("카메라가 초기화되지 않았습니다.");
    const samples: GazeFeatures[] = [];
    const startedAt = performance.now();
    let lastSampleAt = 0;

    await new Promise<void>((resolve, reject) => {
      const collect = (timestamp: number) => {
        try {
          if (timestamp - lastSampleAt >= this.config.sample_interval_ms) {
            lastSampleAt = timestamp;
            const landmarks = this.landmarker.detect(this.video!, timestamp).faceLandmarks[0];
            if (landmarks) samples.push(this.gazeAnalyzer.extract(landmarks));
          }
          if (performance.now() - startedAt >= 2_000) resolve();
          else requestAnimationFrame(collect);
        } catch (error) {
          reject(error);
        }
      };
      requestAnimationFrame(collect);
    });

    this.baseline = this.gazeAnalyzer.calibrate(samples);
    return this.baseline;
  }

  startAnswer(): void {
    if (!this.video || !this.baseline) throw new Error("답변 시작 전에 시선 캘리브레이션이 필요합니다.");
    this.aggregator.reset();
    this.running = true;
    this.hasActiveAnswer = true;
    this.lastSampleAt = 0;
    this.animationFrame = requestAnimationFrame(this.analyzeFrame);
  }

  finishAnswer(): DeliveryMetrics {
    if (!this.hasActiveAnswer) return { measurable: false, frontal_ratio: null, gaze_away_count: null };
    this.stopLoop();
    this.hasActiveAnswer = false;
    return this.aggregator.finalize();
  }

  cancelAnswer(): void {
    this.stopLoop();
    this.hasActiveAnswer = false;
    this.aggregator.reset();
  }

  dispose(): void {
    this.cancelAnswer();
    this.landmarker.dispose();
    this.video = null;
    this.baseline = null;
  }

  private readonly analyzeFrame = (timestamp: number): void => {
    if (!this.running || !this.video) return;
    if (timestamp - this.lastSampleAt >= this.config.sample_interval_ms) {
      this.lastSampleAt = timestamp;
      try {
        this.processResult(this.landmarker.detect(this.video, timestamp));
      } catch {
        this.aggregator.add({ face_detected: false });
      }
    }
    this.animationFrame = requestAnimationFrame(this.analyzeFrame);
  };

  private processResult(result: FaceLandmarkerResult): void {
    const landmarks = result.faceLandmarks[0];
    if (!landmarks || !this.baseline) {
      this.aggregator.add({ face_detected: false });
      return;
    }
    const gaze = this.gazeAnalyzer.extract(landmarks);
    this.aggregator.add({
      face_detected: true,
      looking_at_camera: this.gazeAnalyzer.isLookingAtCamera(gaze, this.baseline),
    });
  }

  private stopLoop(): void {
    this.running = false;
    if (this.animationFrame !== null) cancelAnimationFrame(this.animationFrame);
    this.animationFrame = null;
  }
}
