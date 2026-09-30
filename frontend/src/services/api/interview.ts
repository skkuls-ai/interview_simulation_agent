import type { InterviewQuestion, InterviewResult, SessionSetup } from "../../types/interview";
import { apiRequest } from "./client";

export interface InterviewStatusResponse {
  status: "PREPARING" | "READY" | "IN_PROGRESS" | "EVALUATING" | "COMPLETED" | "FAILED";
  steps: Array<{ step_id: string; label: string; state: "PENDING" | "RUNNING" | "DONE"; detail: string | null }>;
  questions: InterviewQuestion[] | null;
}

export interface DeliveryMetrics {
  measurable: boolean;
  frontal_ratio: number | null;
  gaze_away_count: number | null;
}

export async function createSession(setup: SessionSetup) {
  const form = new FormData();
  form.set("privacy_consent", String(setup.privacyConsent));

  const appendDocument = (name: string, document: SessionSetup[keyof Omit<SessionSetup, "privacyConsent">]) => {
    if (document.file) form.set(`${name}_file`, document.file);
    else form.set(`${name}_text`, document.text);
  };

  appendDocument("resume", setup.resume);
  appendDocument("job_posting", setup.jobPosting);
  appendDocument("job_description", setup.jobDescription);
  appendDocument("cover_letter", setup.coverLetter);

  return apiRequest<{ session_id: string; status: "PREPARING" }>("/api/interviews", { method: "POST", body: form });
}

export function getInterview(sessionId: string) {
  return apiRequest<InterviewStatusResponse>(`/api/interviews/${encodeURIComponent(sessionId)}`);
}

export async function submitAnswer(sessionId: string, input: { question_id: string; audio: Blob | null; duration_sec: number; timed_out: boolean; delivery_metrics: DeliveryMetrics }) {
  const form = new FormData();
  form.set("question_id", input.question_id);
  form.set("duration_sec", String(input.duration_sec));
  form.set("timed_out", String(input.timed_out));
  form.set("delivery_metrics", JSON.stringify(input.delivery_metrics));
  if (input.audio) form.set("audio", input.audio, "answer.webm");
  return apiRequest<{ question_id: string; received: boolean; next_question_id: string | null; status: "IN_PROGRESS" | "EVALUATING" }>(`/api/interviews/${encodeURIComponent(sessionId)}/answers`, { method: "POST", body: form });
}

export function getReport(sessionId: string) {
  return apiRequest<InterviewResult>(`/api/interviews/${encodeURIComponent(sessionId)}/report`);
}
