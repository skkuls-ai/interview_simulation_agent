import { Check, FileSearch, LoaderCircle, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell } from "../components/AppShell";

interface EvaluationScreenProps { onComplete: () => void }

const steps = [
  ["답변 변환 중", "녹음한 답변을 텍스트로 옮깁니다."],
  ["태도 분석 중", "시선 정면 유지와 답변 시간을 살펴봅니다."],
  ["직무 적합성 분석 중", "답변이 공고의 요구사항과 맞는지 확인합니다."],
  ["답변 일관성 분석 중", "서류 내용과 답변이 일치하는지 확인합니다."],
  ["피드백 정리 중", "질문별 피드백을 정리합니다."],
] as const;

export function EvaluationScreen({ onComplete }: EvaluationScreenProps) {
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (active >= steps.length) return;
    const timer = window.setTimeout(() => setActive((value) => value + 1), 650);
    return () => window.clearTimeout(timer);
  }, [active]);

  const completed = active >= steps.length;
  return (
    <AppShell title={completed ? "피드백 준비가 끝났어요" : "면접 결과를 정리하고 있어요"} description="답변의 근거를 확인하고 직무 적합성과 일관성을 함께 살펴봅니다.">
      <section className="process-card panel">
        <div className="process-visual"><span className="orbit orbit-one" /><span className="orbit orbit-two" />{completed ? <Check size={30} /> : <Sparkles size={30} />}</div>
        <div className="process-steps">
          {steps.map(([title, detail], index) => {
            const state = index < active ? "is-done" : index === active ? "is-active" : "";
            return <div className={`process-step ${state}`} key={title}><span>{index < active ? <Check size={17} /> : index === active ? <LoaderCircle className="spin-icon" size={17} /> : <FileSearch size={17} />}</span><div><strong>{title}</strong><p>{detail}</p></div></div>;
          })}
        </div>
        <button className="button button-primary" type="button" disabled={!completed} onClick={onComplete}>피드백 보기</button>
      </section>
    </AppShell>
  );
}
