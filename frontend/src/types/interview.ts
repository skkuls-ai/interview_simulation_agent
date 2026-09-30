export type AppStep =
  | "START"
  | "DOCUMENT_UPLOAD"
  | "PREPARING"
  | "DEVICE_CHECK"
  | "INTERVIEW"
  | "EVALUATING"
  | "REPORT";

export type QuestionType = "INTRO" | "BEHAVIOR" | "TECH";

export interface InterviewQuestion {
  question_id: string;
  order: number;
  type: QuestionType;
  text: string;
}

export interface DocumentInput {
  file: File | null;
  text: string;
}

export interface SessionSetup {
  privacyConsent: boolean;
  resume: DocumentInput;
  jobPosting: DocumentInput;
  jobDescription: DocumentInput;
  coverLetter: DocumentInput;
}

export type Verdict = "충분" | "보완 필요" | "미흡" | "판단 보류";

export interface QuestionFeedback {
  question_id: string;
  question: string;
  answer: string | null;
  strengths: string[];
  gaps: string[];
  next_action: string;
}

export interface InterviewResult {
  summary: string;
  attitude: {
    advice: string[];
    frontal_ratio: number | null;
    gaze_away_count: number | null;
    timed_out_count: number;
  };
  job_fit: { verdict: Verdict; reason: string; quote: string };
  consistency: { verdict: Verdict; reason: string; quote: string };
  per_question: QuestionFeedback[];
}
