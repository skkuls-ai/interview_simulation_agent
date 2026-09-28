import type { AnswerIdentity, PerceptionResult, VisualMetrics } from "../perception";
import type { RecordedAudio } from "../recording";

export interface AnalyzeAnswerRequest {
  identity: AnswerIdentity;
  audio: RecordedAudio;
  duration_seconds: number;
  visual: VisualMetrics | null;
}

/** 녹음과 시각 분석 결과를 백엔드 Perception API로 전송합니다. */
export class PerceptionApiClient {
  constructor(private readonly endpoint = "/api/perception/analyze") {}

  async analyze(request: AnalyzeAnswerRequest): Promise<PerceptionResult> {
    const form = new FormData();
    form.set("session_id", request.identity.session_id);
    form.set("question_id", request.identity.question_id);
    form.set("answer_id", request.identity.answer_id);
    form.set("duration_seconds", request.duration_seconds.toFixed(3));
    if (request.visual) form.set("visual_metrics", JSON.stringify(request.visual));
    form.set("audio", request.audio.blob, request.audio.file_name);

    const response = await fetch(this.endpoint, { method: "POST", body: form });
    if (!response.ok) {
      const body = await response.json().catch(() => null) as { detail?: string } | null;
      throw new Error(body?.detail ?? `분석 API 오류 (${response.status})`);
    }
    return response.json() as Promise<PerceptionResult>;
  }
}
