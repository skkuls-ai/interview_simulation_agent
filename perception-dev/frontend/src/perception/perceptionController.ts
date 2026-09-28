import type { FaceLandmarkerResult } from "@mediapipe/tasks-vision";
import type { PerceptionConfig } from "./config";
import { DEFAULT_PERCEPTION_CONFIG } from "./config";
import { BlendshapeExpressionAnalyzer, type BlendshapeScores } from "./expressionAnalyzer";
import { MediaPipeFaceLandmarkerAdapter, type FaceLandmarkerAdapter } from "./faceLandmarker";
import { IrisGazeAnalyzer, type GazeFeatures } from "./gazeAnalyzer";
import type { GazeBaseline, VisualMetrics } from "./types";
import { AnswerVisualAggregator } from "./visualAggregator";

export interface AnswerIdentity {
  session_id: string;
  question_id: string;
  answer_id: string;
}

/** 최종 면접 UI가 의존하게 될 유일한 시각 분석 인터페이스입니다. */
export interface PerceptionController {
  initialize(video: HTMLVideoElement): Promise<void>;
  calibrate(): Promise<GazeBaseline>;
  startAnswer(identity: AnswerIdentity): void;
  finishAnswer(): VisualMetrics | null;
  cancelAnswer(): void;
  dispose(): void;
}

export class BrowserPerceptionController implements PerceptionController {
  private video: HTMLVideoElement | null = null;
  private baseline: GazeBaseline | null = null;
  private running = false;
  private hasActiveAnswer = false;
  private animationFrame: number | null = null;
  private lastSampleAt = 0;

  private readonly gazeAnalyzer: IrisGazeAnalyzer;
  private readonly expressionAnalyzer: BlendshapeExpressionAnalyzer;
  private readonly aggregator: AnswerVisualAggregator;

  constructor(
    private readonly config: PerceptionConfig = DEFAULT_PERCEPTION_CONFIG,
    private readonly landmarker: FaceLandmarkerAdapter = new MediaPipeFaceLandmarkerAdapter(),
  ) {
    this.gazeAnalyzer = new IrisGazeAnalyzer(config);
    this.expressionAnalyzer = new BlendshapeExpressionAnalyzer();
    this.aggregator = new AnswerVisualAggregator(config);
  }

  async initialize(video: HTMLVideoElement): Promise<void> {
    this.video = video;
    await this.landmarker.initialize();
  }

  async calibrate(): Promise<GazeBaseline> {
    if (!this.video) throw new Error("카메라가 초기화되지 않았습니다.");
    const video = this.video;

    const samples: GazeFeatures[] = [];
    const startedAt = performance.now();
    let lastSampleAt = 0;

    await new Promise<void>((resolve, reject) => {
      const collect = (timestamp: number) => {
        try {
          if (timestamp - lastSampleAt >= this.config.sample_interval_ms) {
            lastSampleAt = timestamp;
            const result = this.landmarker.detect(video, timestamp);
            const landmarks = result.faceLandmarks[0];
            if (landmarks) {
              samples.push(this.gazeAnalyzer.extract(landmarks));
            }
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

  startAnswer(_identity: AnswerIdentity): void {
    if (!this.video) throw new Error("카메라가 초기화되지 않았습니다.");
    if (!this.baseline) throw new Error("답변 시작 전에 시선 캘리브레이션이 필요합니다.");
    if (this.running) throw new Error("이미 답변 분석이 진행 중입니다.");

    this.aggregator.reset();
    this.running = true;
    this.hasActiveAnswer = true;
    this.lastSampleAt = 0;
    this.animationFrame = requestAnimationFrame(this.analyzeFrame);
  }

  finishAnswer(): VisualMetrics | null {
    if (!this.hasActiveAnswer) throw new Error("진행 중인 답변 분석이 없습니다.");
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
      } catch (error) {
        console.warn("시각 프레임 분석을 건너뜁니다.", error);
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

    const categories = result.faceBlendshapes[0]?.categories ?? [];
    const blendshapes: BlendshapeScores = Object.fromEntries(
      categories.map((category) => [category.categoryName, category.score]),
    );
    const expression = this.expressionAnalyzer.analyze(blendshapes);
    const gaze = this.gazeAnalyzer.extract(landmarks);

    this.aggregator.add({
      face_detected: true,
      looking_at_camera: this.gazeAnalyzer.isLookingAtCamera(gaze, this.baseline),
      blendshapes: expression.tracked_scores,
    });
  }

  private stopLoop(): void {
    this.running = false;
    if (this.animationFrame !== null) cancelAnimationFrame(this.animationFrame);
    this.animationFrame = null;
  }
}
