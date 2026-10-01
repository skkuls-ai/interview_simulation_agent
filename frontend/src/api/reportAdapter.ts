import type { InterviewResult, Verdict } from "../types/interview";

/** 서버 GET /report 응답(ReportResponse) 중 화면이 쓰는 부분. */
export interface ReportResponse {
  session_id: string;
  attitude: {
    metrics: {
      speech?: { words_per_min: number | null; filler_count: number | null };
      gaze?: { measurable: boolean; frontal_ratio: number | null; gaze_away_count: number | null };
      time?: {
        timed_out_count: number;
        per_question?: Array<{ question_id: string; duration_sec: number; timed_out: boolean }>;
      };
    };
    advice: string[];
    quotes?: Array<{ question_id: string; text: string }>;
  };
  job_fit: FitFeedback;
  consistency: FitFeedback;
  per_question: Array<{
    question_id: string; strengths: string[]; gaps: string[]; next_action: string;
    linked_claim_ids?: string[]; linked_checkpoint_ids?: string[];
  }>;
  questions: Array<{ question_id: string; text: string; answer_text: string | null }>;
  requirements?: Array<{ requirement_id: string; text: string }>;
  claims?: Array<{ claim_id: string; text: string }>;
  checkpoints?: Array<{ checkpoint_id: string; title: string }>;
}

interface FitFeedback {
  verdict: "SUFFICIENT" | "NEEDS_WORK" | "INSUFFICIENT" | "WITHHELD";
  reason: string;
  quotes: Array<{ text: string }>;
  refs?: string[];
}

const VERDICT_LABEL: Record<FitFeedback["verdict"], Verdict> = {
  SUFFICIENT: "충분",
  NEEDS_WORK: "보완 필요",
  INSUFFICIENT: "미흡",
  WITHHELD: "판단 보류",
};

/** ReportResponse를 결과 화면이 읽는 InterviewResult 모양으로 바꿉니다. */
export function toInterviewResult(report: ReportResponse): InterviewResult {
  const gaze = report.attitude.metrics.gaze;
  const measurable = gaze?.measurable ?? false;
  const speech = report.attitude.metrics.speech;
  const byId = new Map(report.questions.map((q) => [q.question_id, q]));
  const timeById = new Map((report.attitude.metrics.time?.per_question ?? []).map((t) => [t.question_id, t]));
  // ID → 화면 문구 (ID 자체는 화면에 보여주지 않는다)
  const reqText = new Map((report.requirements ?? []).map((r) => [r.requirement_id, r.text]));
  const claimText = new Map((report.claims ?? []).map((c) => [c.claim_id, c.text]));
  const cpTitle = new Map((report.checkpoints ?? []).map((c) => [c.checkpoint_id, c.title]));
  const texts = (ids: string[] | undefined, map: Map<string, string>) =>
    (ids ?? []).map((id) => map.get(id)).filter((t): t is string => Boolean(t));

  const fit = (f: FitFeedback, refText: Map<string, string>) => ({
    verdict: VERDICT_LABEL[f.verdict] ?? "판단 보류",
    reason: f.reason,
    quote: f.quotes[0]?.text ?? "",
    quotes: f.quotes.map((q) => q.text),
    evidence: texts(f.refs, refText),
  });

  return {
    summary: report.attitude.advice[0] ?? report.job_fit.reason,
    attitude: {
      advice: report.attitude.advice,
      frontal_ratio: measurable ? gaze?.frontal_ratio ?? null : null,
      gaze_away_count: measurable ? gaze?.gaze_away_count ?? null : null,
      timed_out_count: report.attitude.metrics.time?.timed_out_count ?? 0,
      words_per_min: speech?.words_per_min ?? null,
      filler_count: speech?.filler_count ?? null,
      quotes: (report.attitude.quotes ?? []).map((q) => ({ question_id: q.question_id, text: q.text })),
    },
    job_fit: fit(report.job_fit, reqText),        // 근거: 요구사항 문구
    consistency: fit(report.consistency, claimText), // 근거: 서류 주장 문구
    per_question: report.per_question.map((item) => ({
      question_id: item.question_id,
      question: byId.get(item.question_id)?.text ?? item.question_id,
      answer: byId.get(item.question_id)?.answer_text ?? null,
      strengths: item.strengths,
      gaps: item.gaps,
      next_action: item.next_action,
      duration_sec: timeById.get(item.question_id)?.duration_sec,
      timed_out: timeById.get(item.question_id)?.timed_out,
      linked_claims: texts(item.linked_claim_ids, claimText),
      linked_checkpoints: texts(item.linked_checkpoint_ids, cpTitle),
    })),
  };
}
