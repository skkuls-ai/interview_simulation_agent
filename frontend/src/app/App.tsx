import { useState } from "react";
import { mockPrompts, mockResult } from "../mocks/interview";
import { AnalysisScreen } from "../screens/AnalysisScreen";
import { DeviceCheckScreen } from "../screens/DeviceCheckScreen";
import { EvaluationScreen } from "../screens/EvaluationScreen";
import { InterviewScreen } from "../screens/InterviewScreen";
import { ResultScreen } from "../screens/ResultScreen";
import { SetupScreen } from "../screens/SetupScreen";
import type { AppStep, SessionSetup } from "../types/interview";

export function App() {
  const [step, setStep] = useState<AppStep>("SETUP");
  const [promptIndex, setPromptIndex] = useState(0);

  const startAnalysis = (_setup: SessionSetup) => {
    // TODO: createSession을 호출한 뒤 서버의 분석 상태를 구독합니다.
    setStep("ANALYZING");
  };

  const completeAnswer = () => {
    if (promptIndex < mockPrompts.length - 1) {
      setPromptIndex((index) => index + 1);
      return;
    }
    setStep("EVALUATING");
  };

  const restart = () => {
    setPromptIndex(0);
    setStep("SETUP");
  };

  switch (step) {
    case "SETUP":
      return <SetupScreen onSubmit={startAnalysis} />;
    case "ANALYZING":
      return <AnalysisScreen onComplete={() => setStep("DEVICE_CHECK")} />;
    case "DEVICE_CHECK":
      return <DeviceCheckScreen onComplete={() => setStep("INTERVIEW")} />;
    case "INTERVIEW":
      return (
        <InterviewScreen
          key={mockPrompts[promptIndex].id}
          prompt={mockPrompts[promptIndex]}
          current={promptIndex + 1}
          total={mockPrompts.length}
          onAnswerComplete={completeAnswer}
        />
      );
    case "EVALUATING":
      return <EvaluationScreen onComplete={() => setStep("RESULT")} />;
    case "RESULT":
      return <ResultScreen result={mockResult} onRestart={restart} />;
  }
}
