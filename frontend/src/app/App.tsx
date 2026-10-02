import { useEffect, useState } from "react";
import { StepContext } from "../components/StepProgress";
import { mockQuestions, mockResult } from "../mocks/interview";
import { AnalysisScreen } from "../pages/AnalysisScreen";
import { DeviceCheckScreen } from "../pages/DeviceCheckScreen";
import { EvaluationScreen } from "../pages/EvaluationScreen";
import { InterviewEndScreen } from "../pages/InterviewEndScreen";
import { InterviewScreen, type CapturedAnswer } from "../pages/InterviewScreen";
import { ResultScreen } from "../pages/ResultScreen";
import { SetupScreen } from "../pages/SetupScreen";
import { StartScreen } from "../pages/StartScreen";
import { ApiError } from "../api/client";
import { createSession, getReport, submitAnswer, type InterviewStatusResponse } from "../api/interview";
import { toInterviewResult } from "../api/reportAdapter";
import type { AppStep, InterviewQuestion, InterviewResult, SessionSetup } from "../types/interview";

const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

export function App() {
  const [step, setStep] = useState<AppStep>("START");
  const [questionIndex, setQuestionIndex] = useState(0);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [questions, setQuestions] = useState<InterviewQuestion[]>(mockQuestions);
  const [result, setResult] = useState<InterviewResult>(mockResult);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }, [step, questionIndex]);

  const startAnalysis = async (setup: SessionSetup) => {
    if (!USE_MOCK) {
      const session = await createSession(setup);
      setSessionId(session.session_id);
    }
    setStep("PREPARING");
  };

  const finishPreparing = (status: InterviewStatusResponse | null) => {
    if (status?.questions?.length) setQuestions(status.questions);
    setStep("DEVICE_CHECK");
  };

  const finishEvaluating = async () => {
    if (!USE_MOCK && sessionId) {
      try {
        setResult(toInterviewResult(await getReport(sessionId)));
      } catch {
        goToUpload();
        return;
      }
    }
    setStep("REPORT");
  };

  const completeAnswer = async (answer: CapturedAnswer) => {
    const question = questions[questionIndex];
    if (!USE_MOCK && sessionId) {
      try {
        await submitAnswer(sessionId, { question_id: question.question_id, ...answer });
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          window.alert("서버에서 면접 정보를 찾을 수 없습니다. 처음부터 다시 시작해 주세요.");
          goToUpload();
          return;
        }
        throw error;
      }
    }
    if (questionIndex < questions.length - 1) {
      setQuestionIndex((index) => index + 1);
      return;
    }
    setStep("INTERVIEW_END");
  };

  const goToUpload = () => { setQuestionIndex(0); setSessionId(null); setQuestions(mockQuestions); setStep("DOCUMENT_UPLOAD"); };
  const retryInterview = () => { setQuestionIndex(0); setStep("DEVICE_CHECK"); };

  const renderStep = () => {
    switch (step) {
      case "START":
        return <StartScreen onStart={() => setStep("DOCUMENT_UPLOAD")} />;
      case "DOCUMENT_UPLOAD":
        return <SetupScreen onSubmit={startAnalysis} />;
      case "PREPARING":
        return <AnalysisScreen sessionId={USE_MOCK ? null : sessionId} onComplete={finishPreparing} onFail={goToUpload} />;
      case "DEVICE_CHECK":
        return <DeviceCheckScreen onComplete={() => setStep("INTERVIEW")} />;
      case "INTERVIEW":
        return (
          <InterviewScreen
            key={questions[questionIndex].question_id}
            question={questions[questionIndex]}
            current={questionIndex + 1}
            total={questions.length}
            onAnswerComplete={completeAnswer}
          />
        );
      case "INTERVIEW_END":
        return <InterviewEndScreen onComplete={() => setStep("EVALUATING")} />;
      case "EVALUATING":
        return <EvaluationScreen sessionId={USE_MOCK ? null : sessionId} onComplete={finishEvaluating} onFail={goToUpload} />;
      case "REPORT":
        return <ResultScreen result={result} onRetry={retryInterview} onRestart={goToUpload} />;
    }
  };

  return <StepContext.Provider value={step}>{renderStep()}</StepContext.Provider>;
}
