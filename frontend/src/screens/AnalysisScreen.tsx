import { Check, FileSearch, LoaderCircle, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell } from "../components/AppShell";

interface AnalysisScreenProps { onComplete: () => void }

const steps = [
  ["채용공고 읽는 중", "직무 요구사항과 인재상을 확인합니다."],
  ["이력서·자기소개서 읽는 중", "경험과 확인할 주장을 찾습니다."],
  ["공고와 경험 연결 중", "요구사항과 관련 경험을 연결합니다."],
  ["검증 포인트 찾는 중", "면접에서 확인할 내용을 정리합니다."],
  ["질문 준비 중", "고정 순서의 질문 다섯 개를 만듭니다."],
  ["질문 검수 중", "질문 수와 연결 정보의 유효성을 확인합니다."],
] as const;

export function AnalysisScreen({ onComplete }: AnalysisScreenProps) {
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (active >= steps.length) return;
    const timer = window.setTimeout(() => setActive((value) => value + 1), 650);
    return () => window.clearTimeout(timer);
  }, [active]);

  const completed = active >= steps.length;
  return (
    <AppShell title={completed ? "맞춤 면접 준비가 끝났어요" : "맞춤 면접을 설계하고 있어요"} description="질문 내용과 평가 기준은 면접이 끝날 때까지 공개하지 않습니다.">
      <section className="process-card panel">
        <div className="process-visual"><span className="orbit orbit-one" /><span className="orbit orbit-two" />{completed ? <Check size={30} /> : <Sparkles size={30} />}</div>
        <div className="process-steps">
          {steps.map(([title, detail], index) => {
            const state = index < active ? "is-done" : index === active ? "is-active" : "";
            return <div className={`process-step ${state}`} key={title}><span>{index < active ? <Check size={17} /> : index === active ? <LoaderCircle className="spin-icon" size={17} /> : <FileSearch size={17} />}</span><div><strong>{title}</strong><p>{detail}</p></div></div>;
          })}
        </div>
        <button className="button button-primary" type="button" disabled={!completed} onClick={onComplete}>면접 대기실로</button>
      </section>
    </AppShell>
  );
}
