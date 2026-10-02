export type AppStep =
  | "START"
  | "DOCUMENT_UPLOAD"
  | "PREPARING"
  | "DEVICE_CHECK"
  | "INTERVIEW"
  | "INTERVIEW_END"
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
  duration_sec?: number;          // 2. 질문별 답변 시간
  timed_out?: boolean;
  linked_claims?: string[];       // 4. 연결된 서류 주장 (문구)
  linked_checkpoints?: string[];  // 4. 확인 포인트 (제목)
}

export interface InterviewResult {
  summary: string;
  attitude: {
    advice: string[];
    frontal_ratio: number | null;
    gaze_away_count: number | null;
    timed_out_count: number;
    words_per_min?: number | null;  // 1. 인식된 답변이 없으면 null
    filler_count?: number | null;   // 1.
    quotes?: Array<{ question_id: string; text: string }>;  // 3.
  };
  job_fit: { verdict: Verdict; reason: string; quote: string; quotes?: string[]; evidence?: string[] };
  consistency: { verdict: Verdict; reason: string; quote: string; quotes?: string[]; evidence?: string[] };
  per_question: QuestionFeedback[];
}
