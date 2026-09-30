import { Check, LoaderCircle, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell } from "../components/AppShell";

interface EvaluationScreenProps { onComplete: () => void }

const steps = ["답변 변환 중", "태도 분석 중", "직무 적합성 분석 중", "답변 일관성 분석 중", "피드백 정리 중"];

export function EvaluationScreen({ onComplete }: EvaluationScreenProps) {
  const [active, setActive] = useState(0);
  useEffect(() => {
    if (active >= steps.length) return;
    const timer = window.setTimeout(() => setActive((value) => value + 1), 700);
    return () => window.clearTimeout(timer);
  }, [active]);

  const completed = active >= steps.length;
  return (
    <AppShell title={completed ? "피드백 준비가 끝났어요" : "면접 결과를 정리하고 있어요"} description="답변의 근거를 확인하고 직무 적합성과 일관성을 함께 살펴봅니다.">
      <section className="process-card panel evaluation-card">
        <div className="evaluation-symbol">{completed ? <Check size={34} /> : <LoaderCircle size={34} />}<Sparkles size={18} /></div>
        <div className="evaluation-meter"><span style={{ width: `${Math.min(100, active / steps.length * 100)}%` }} /></div>
        <div className="evaluation-list">
          {steps.map((label, index) => <span className={index === active ? "is-processing" : ""} key={label}>{index < active ? <Check size={16} /> : <LoaderCircle size={16} />} {label}</span>)}
        </div>
        <button className="button button-primary" type="button" disabled={!completed} onClick={onComplete}>피드백 보기</button>
      </section>
    </AppShell>
  );
}
