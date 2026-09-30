import { Check, FileSearch, LoaderCircle, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell } from "../components/AppShell";
import { useSessionStatus } from "../api/useSessionStatus";
import type { InterviewStatusResponse } from "../api/interview";

interface EvaluationScreenProps {
  /** null이면 mock 진행(타이머), 값이 있으면 서버 상태를 2초마다 읽습니다. */
  sessionId: string | null;
  onComplete: (status: InterviewStatusResponse) => void;
  onFail: () => void;
}

const steps = [
  ["답변 변환 중", "녹음한 답변을 텍스트로 옮깁니다."],
  ["태도 분석 중", "시선 정면 유지와 답변 시간을 살펴봅니다."],
  ["직무 적합성 분석 중", "답변이 공고의 요구사항과 맞는지 확인합니다."],
  ["답변 일관성 분석 중", "서류 내용과 답변이 일치하는지 확인합니다."],
  ["피드백 정리 중", "질문별 피드백을 정리합니다."],
] as const;

export function EvaluationScreen({ sessionId, onComplete, onFail }: EvaluationScreenProps) {
  const [active, setActive] = useState(0);
  const server = useSessionStatus(sessionId, (status) => status === "COMPLETED");

  useEffect(() => {
    if (sessionId || active >= steps.length) return;
    const timer = window.setTimeout(() => setActive((value) => value + 1), 650);
    return () => window.clearTimeout(timer);
  }, [active, sessionId]);

  const failed = server?.status === "FAILED";
  const completed = sessionId ? server?.status === "COMPLETED" : active >= steps.length;
  const rows = sessionId && server && server.steps.length > 0
    ? server.steps.map((step) => ({ title: step.label, detail: step.detail ?? "", state: step.state === "DONE" ? "is-done" : step.state === "RUNNING" ? "is-active" : "" }))
    : steps.map(([title, detail], index) => ({ title, detail, state: sessionId ? "" : index < active ? "is-done" : index === active ? "is-active" : "" }));
  return (
    <AppShell title={failed ? "처리 중 문제가 생겼어요" : completed ? "피드백 준비가 끝났어요" : "면접 결과를 정리하고 있어요"} description="답변의 근거를 확인하고 직무 적합성과 일관성을 함께 살펴봅니다.">
      <section className="process-card panel">
        {failed && <p role="alert">{server?.error ?? "잠시 후 다시 시도해 주세요."}</p>}
        <div className="process-visual"><span className="orbit orbit-one" /><span className="orbit orbit-two" />{completed ? <Check size={30} /> : <Sparkles size={30} />}</div>
        <div className="process-steps">
          {rows.map((row) => (
            <div className={`process-step ${row.state}`} key={row.title}>
              <span>{row.state === "is-done" ? <Check size={17} /> : row.state === "is-active" ? <LoaderCircle className="spin-icon" size={17} /> : <FileSearch size={17} />}</span>
              <div><strong>{row.title}</strong><p>{row.detail}</p></div>
            </div>
          ))}
        </div>
        <button className="button button-primary" type="button" disabled={!completed && !failed} onClick={() => (failed ? onFail() : onComplete(server as InterviewStatusResponse))}>{failed ? "처음으로 돌아가기" : "피드백 보기"}</button>
      </section>
    </AppShell>
  );
}
