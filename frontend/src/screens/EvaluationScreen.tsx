import { Check, LoaderCircle, Sparkles } from "lucide-react";
import { AppShell } from "../components/AppShell";

interface EvaluationScreenProps { onComplete: () => void; }

export function EvaluationScreen({ onComplete }: EvaluationScreenProps) {
  return (
    <AppShell title="면접 결과를 정리하고 있어요" description="문항별 평가를 모아 강점과 개선 방향을 찾고 있습니다.">
      <section className="process-card panel evaluation-card">
        <div className="evaluation-symbol"><LoaderCircle size={34} /><Sparkles size={18} /></div>
        <div className="evaluation-meter"><span /></div>
        <div className="evaluation-list">
          <span><Check size={16} /> 답변 내용과 근거 확인</span>
          <span><Check size={16} /> 직무 역량 기준 종합</span>
          <span className="is-processing"><LoaderCircle size={16} /> 전달 방식 피드백 생성</span>
        </div>
        <p className="process-note">실제 연동 시 백그라운드 평가 완료 이벤트를 기다립니다.</p>
        <button className="button button-secondary" type="button" onClick={onComplete}>결과 화면 확인</button>
      </section>
    </AppShell>
  );
}
