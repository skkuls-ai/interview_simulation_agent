import { useState } from "react";
import { mockQuestions, mockResult } from "../mocks/interview";
import { AnalysisScreen } from "../screens/AnalysisScreen";
import { DeviceCheckScreen } from "../screens/DeviceCheckScreen";
import { EvaluationScreen } from "../screens/EvaluationScreen";
import { InterviewScreen, type CapturedAnswer } from "../screens/InterviewScreen";
import { ResultScreen } from "../screens/ResultScreen";
import { SetupScreen } from "../screens/SetupScreen";
import { StartScreen } from "../screens/StartScreen";
import { createSession, submitAnswer } from "../services/api/interview";
import type { AppStep, SessionSetup } from "../types/interview";

const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

export function App() {
  const [step, setStep] = useState<AppStep>("START");
  const [questionIndex, setQuestionIndex] = useState(0);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const startAnalysis = async (setup: SessionSetup) => {
    if (!USE_MOCK) {
      const session = await createSession(setup);
      setSessionId(session.session_id);
    }
    setStep("PREPARING");
  };

  const completeAnswer = async (answer: CapturedAnswer) => {
    const question = mockQuestions[questionIndex];
    if (!USE_MOCK && sessionId) {
      await submitAnswer(sessionId, { question_id: question.question_id, ...answer });
    }
    if (questionIndex < mockQuestions.length - 1) {
      setQuestionIndex((index) => index + 1);
      return;
    }
    setStep("EVALUATING");
  };

  const goToUpload = () => { setQuestionIndex(0); setStep("DOCUMENT_UPLOAD"); };
  const retryInterview = () => { setQuestionIndex(0); setStep("DEVICE_CHECK"); };

  switch (step) {
    case "START":
      return <StartScreen onStart={() => setStep("DOCUMENT_UPLOAD")} />;
    case "DOCUMENT_UPLOAD":
      return <SetupScreen onSubmit={startAnalysis} />;
    case "PREPARING":
      return <AnalysisScreen onComplete={() => setStep("DEVICE_CHECK")} />;
    case "DEVICE_CHECK":
      return <DeviceCheckScreen onComplete={() => setStep("INTERVIEW")} />;
    case "INTERVIEW":
      return (
        <InterviewScreen
          key={mockQuestions[questionIndex].question_id}
          question={mockQuestions[questionIndex]}
          current={questionIndex + 1}
          total={mockQuestions.length}
          onAnswerComplete={completeAnswer}
        />
      );
    case "EVALUATING":
      return <EvaluationScreen onComplete={() => setStep("REPORT")} />;
    case "REPORT":
      return <ResultScreen result={mockResult} onRetry={retryInterview} onRestart={goToUpload} />;
  }
}
