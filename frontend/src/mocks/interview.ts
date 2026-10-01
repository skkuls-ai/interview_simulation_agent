import type { InterviewQuestion, InterviewResult } from "../types/interview";

export const mockQuestions: InterviewQuestion[] = [
  { question_id: "Q-1", order: 1, type: "INTRO", text: "지원한 직무와 관련된 경험을 중심으로 자기소개를 해주세요." },
  { question_id: "Q-2", order: 2, type: "BEHAVIOR", text: "목표를 달성하기 위해 주도적으로 문제를 해결한 경험을 말씀해 주세요." },
  { question_id: "Q-3", order: 3, type: "BEHAVIOR", text: "협업 과정에서 의견 충돌을 조율했던 경험과 그 결과를 설명해 주세요." },
  { question_id: "Q-4", order: 4, type: "TECH", text: "프로젝트에서 성능 문제를 발견하고 개선한 과정을 기술적으로 설명해 주세요." },
  { question_id: "Q-5", order: 5, type: "TECH", text: "지원 직무에서 본인의 기술적 강점을 어떻게 활용할 수 있다고 생각하나요?" },
];

export const mockResult: InterviewResult = {
  summary: "경험의 맥락과 본인의 역할은 분명했으며, 결과를 직무 요구사항과 더 구체적으로 연결하면 답변의 설득력이 높아집니다.",
  attitude: {
    advice: ["핵심 행동을 먼저 말한 뒤 배경을 설명하면 답변이 더 선명해집니다.", "시선 지표는 안정적이며 면접 전체에서 비슷한 흐름을 유지했습니다."],
    frontal_ratio: 0.82,
    gaze_away_count: 4,
    timed_out_count: 0,
    words_per_min: 96,
    filler_count: 7,
    quotes: [{ question_id: "Q-2", text: "팀원들과 의견을 맞췄던 것 같습니다" }],
  },
  job_fit: { verdict: "보완 필요", reason: "문제 해결 경험은 확인되지만 지원 직무의 핵심 요구사항과 결과의 연결이 다소 약합니다.", quote: "API 응답 속도를 개선하기 위해 캐시 구조를 적용했습니다." },
  consistency: { verdict: "충분", reason: "자기소개서에 작성한 역할과 면접 답변에서 설명한 책임 범위가 일치합니다.", quote: "백엔드 API 설계와 배포 자동화를 담당했습니다." },
  per_question: mockQuestions.map((question, index) => ({
    question_id: question.question_id,
    question: question.text,
    answer: [
      "백엔드 API를 설계하고 배포 자동화를 맡았습니다. 팀 프로젝트에서 검색 결과의 근거를 보여주는 기능을 구현해 사용자가 답변을 확인할 수 있도록 했습니다.",
      "검색 결과가 기대와 다를 때 원인을 찾기 위해 평가 질문을 만들고 결과를 비교했습니다. 청크 크기와 리랭킹 방식을 조정해 검색 정확도를 개선했습니다.",
      null,
      "평가 질문 50개 중 정답 문서가 상위 3개 안에 든 비율을 측정했습니다. 청크 크기를 조정하고 리랭커를 적용해 해당 문항 수를 30개에서 36개로 늘렸습니다.",
      "문제를 수치로 확인하고 작은 실험으로 개선 효과를 비교하는 것이 제 강점입니다. 이 방식을 검색 품질을 지속적으로 높이는 업무에 활용하겠습니다.",
    ][index],
    strengths: ["상황과 본인의 역할을 구분해 설명했습니다."],
    gaps: ["결과를 수치나 구체적인 변화로 보완할 수 있습니다."],
    next_action: "답변 첫 문장에 핵심 성과를 배치해 다시 연습해 보세요.",
    duration_sec: index === 2 ? 12 : 48,
    timed_out: false,
    linked_claims: index === 0 ? ["백엔드 API 설계와 배포 자동화를 담당했습니다"] : [],
    linked_checkpoints: index === 0 ? ["API 응답 속도 개선의 측정 기준"] : [],
  })),
};
