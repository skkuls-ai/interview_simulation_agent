import type { InterviewResult, Verdict } from "../types/interview";

/** 서버 GET /report 응답(ReportResponse) 중 화면이 쓰는 부분. */
export interface ReportResponse {
  session_id: string;
  attitude: {
    metrics: {
      gaze?: { measurable: boolean; frontal_ratio: number | null; gaze_away_count: number | null };
      time?: { timed_out_count: number };
    };
    advice: string[];
  };
  job_fit: FitFeedback;
  consistency: FitFeedback;
  per_question: Array<{ question_id: string; strengths: string[]; gaps: string[]; next_action: string }>;
  questions: Array<{ question_id: string; text: string; answer_text: string | null }>;
}

interface FitFeedback {
  verdict: "SUFFICIENT" | "NEEDS_WORK" | "INSUFFICIENT" | "WITHHELD";
  reason: string;
  quotes: Array<{ text: string }>;
}

const VERDICT_LABEL: Record<FitFeedback["verdict"], Verdict> = {
  SUFFICIENT: "충분",
  NEEDS_WORK: "보완 필요",
  INSUFFICIENT: "미흡",
  WITHHELD: "판단 보류",
};

const fit = (feedback: FitFeedback) => ({
  verdict: VERDICT_LABEL[feedback.verdict] ?? "판단 보류",
  reason: feedback.reason,
  quote: feedback.quotes[0]?.text ?? "",
});

/** ReportResponse를 기존 결과 화면이 읽는 InterviewResult 모양으로 바꿉니다. */
export function toInterviewResult(report: ReportResponse): InterviewResult {
  const gaze = report.attitude.metrics.gaze;
  const measurable = gaze?.measurable ?? false;
  const byId = new Map(report.questions.map((question) => [question.question_id, question]));
  return {
    summary: report.attitude.advice[0] ?? report.job_fit.reason,
    attitude: {
      advice: report.attitude.advice,
      frontal_ratio: measurable ? gaze?.frontal_ratio ?? null : null,
      gaze_away_count: measurable ? gaze?.gaze_away_count ?? null : null,
      timed_out_count: report.attitude.metrics.time?.timed_out_count ?? 0,
    },
    job_fit: fit(report.job_fit),
    consistency: fit(report.consistency),
    per_question: report.per_question.map((item) => ({
      question_id: item.question_id,
      question: byId.get(item.question_id)?.text ?? item.question_id,
      answer: byId.get(item.question_id)?.answer_text ?? null,
      strengths: item.strengths,
      gaps: item.gaps,
      next_action: item.next_action,
    })),
  };
}
