import { useState } from "react";
import { mockQuestions, mockResult } from "../mocks/interview";
import { AnalysisScreen } from "../screens/AnalysisScreen";
import { DeviceCheckScreen } from "../screens/DeviceCheckScreen";
import { EvaluationScreen } from "../screens/EvaluationScreen";
import { InterviewScreen } from "../screens/InterviewScreen";
import { ResultScreen } from "../screens/ResultScreen";
import { SetupScreen } from "../screens/SetupScreen";
import { StartScreen } from "../screens/StartScreen";
import type { AppStep, SessionSetup } from "../types/interview";

export function App() {
  const [step, setStep] = useState<AppStep>("START");
  const [questionIndex, setQuestionIndex] = useState(0);

  const startAnalysis = (_setup: SessionSetup) => {
    // API 연결 후에는 여기서 세션을 만들고 session_id를 저장합니다.
    setStep("PREPARING");
  };

  const completeAnswer = () => {
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
