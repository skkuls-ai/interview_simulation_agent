import { Check, FileSearch, LoaderCircle, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell } from "../components/AppShell";
import { useSessionStatus } from "../api/useSessionStatus";
import type { InterviewStatusResponse } from "../api/interview";

interface AnalysisScreenProps {
  /** null이면 mock 진행(타이머), 값이 있으면 서버 상태를 2초마다 읽습니다. */
  sessionId: string | null;
  onComplete: (status: InterviewStatusResponse) => void;
  onFail: () => void;
}

const steps = [
  ["채용공고 읽는 중", "직무 요구사항과 인재상을 확인합니다."],
  ["이력서·자기소개서 읽는 중", "경험과 확인할 주장을 찾습니다."],
  ["공고와 경험 연결 중", "요구사항과 관련 경험을 연결합니다."],
  ["검증 포인트 찾는 중", "면접에서 확인할 내용을 정리합니다."],
  ["질문 준비 중", "고정 순서의 질문 다섯 개를 만듭니다."],
  ["질문 검수 중", "질문 수와 연결 정보의 유효성을 확인합니다."],
] as const;

export function AnalysisScreen({ sessionId, onComplete, onFail }: AnalysisScreenProps) {
  const [active, setActive] = useState(0);
  const server = useSessionStatus(sessionId, (status) => status === "READY");

  useEffect(() => {
    if (sessionId || active >= steps.length) return;
    const timer = window.setTimeout(() => setActive((value) => value + 1), 650);
    return () => window.clearTimeout(timer);
  }, [active, sessionId]);

  const failed = server?.status === "FAILED";
  const completed = sessionId ? server?.status === "READY" : active >= steps.length;
  const rows = sessionId && server && server.steps.length > 0
    ? server.steps.map((step) => ({ title: step.label, detail: step.detail ?? "", state: step.state === "DONE" ? "is-done" : step.state === "RUNNING" ? "is-active" : "" }))
    : steps.map(([title, detail], index) => ({ title, detail, state: sessionId ? "" : index < active ? "is-done" : index === active ? "is-active" : "" }));
  return (
    <AppShell title={failed ? "처리 중 문제가 생겼어요" : completed ? "맞춤 면접 준비가 끝났어요" : "맞춤 면접을 설계하고 있어요"} description="질문 내용과 평가 기준은 면접이 끝날 때까지 공개하지 않습니다.">
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
        <button className="button button-primary" type="button" disabled={!completed && !failed} onClick={() => (failed ? onFail() : onComplete(server as InterviewStatusResponse))}>{failed ? "처음으로 돌아가기" : "면접 대기실로"}</button>
      </section>
    </AppShell>
  );
}
