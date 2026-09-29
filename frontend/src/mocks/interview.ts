import type { InterviewPrompt, InterviewResult } from "../types/interview";

export const mockPrompts: InterviewPrompt[] = [
  {
    id: "self-intro-1",
    type: "SELF_INTRO",
    text: "지원한 직무와 관련된 경험을 중심으로 자기소개를 해주세요.",
    sequence: 1,
    preparationSeconds: 5,
    softLimitSeconds: 60,
  },
  {
    id: "main-1",
    type: "MAIN_QUESTION",
    text: "목표를 달성하기 위해 주도적으로 문제를 해결한 경험을 말씀해 주세요.",
    sequence: 2,
    preparationSeconds: 5,
    softLimitSeconds: 60,
  },
  {
    id: "follow-up-1",
    type: "FOLLOW_UP",
    text: "그 과정에서 본인이 직접 내린 가장 중요한 결정은 무엇이었나요?",
    sequence: 3,
    preparationSeconds: 5,
    softLimitSeconds: 60,
    parentQuestionId: "main-1",
  },
  {
    id: "closing-1",
    type: "CLOSING",
    text: "마지막으로 강조하고 싶은 내용이 있다면 말씀해 주세요.",
    sequence: 4,
    preparationSeconds: 5,
    softLimitSeconds: 60,
  },
];

export const mockResult: InterviewResult = {
  summary: "답변의 근거와 직무 연결성을 중심으로 종합한 모의 결과입니다.",
  strengths: ["경험의 배경과 본인의 역할을 구분해 설명했습니다."],
  improvements: ["행동의 결과를 수치나 구체적인 변화로 보완해 보세요."],
};
