export type AppStep =
  | "SETUP"
  | "ANALYZING"
  | "DEVICE_CHECK"
  | "INTERVIEW"
  | "EVALUATING"
  | "RESULT";

// 백엔드 prompt.type 확정 전 사용하는 프런트엔드 내부 타입입니다.
export type PromptType =
  | "SELF_INTRO"
  | "MAIN_QUESTION"
  | "FOLLOW_UP"
  | "CLOSING"
  | "NO_RESPONSE_CONFIRM";

export interface InterviewPrompt {
  id: string;
  type: PromptType;
  text: string;
  sequence: number;
  preparationSeconds: number;
  softLimitSeconds: number;
  parentQuestionId?: string;
}

export interface SessionSetup {
  consented: boolean;
  jdFile: File | null;
  resumeFile: File | null;
  coverLetterFile: File | null;
}

export interface InterviewResult {
  summary: string;
  strengths: string[];
  improvements: string[];
}
