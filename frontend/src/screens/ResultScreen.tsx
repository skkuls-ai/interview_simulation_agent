import { Award, RefreshCcw, Sparkles, Target } from "lucide-react";
import { AppShell } from "../components/AppShell";
import type { InterviewResult } from "../types/interview";

interface ResultScreenProps { result: InterviewResult; onRestart: () => void; }

export function ResultScreen({ result, onRestart }: ResultScreenProps) {
  return (
    <AppShell>
      <section className="result-hero">
        <span className="result-icon"><Award size={25} /></span>
        <div><span className="eyebrow">Interview report</span><h1>종합 면접 결과</h1><p>{result.summary}</p></div>
        <div className="result-score"><span>완료한 질문</span><strong>4</strong><small>questions</small></div>
      </section>
      <div className="result-grid">
        <section className="panel feedback-card strength-card">
          <div className="feedback-heading"><span><Sparkles size={20} /></span><div><small>Strength</small><h2>잘한 점</h2></div></div>
          <ul>{result.strengths.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
        <section className="panel feedback-card improvement-card">
          <div className="feedback-heading"><span><Target size={20} /></span><div><small>Next step</small><h2>개선할 점</h2></div></div>
          <ul>{result.improvements.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
      </div>
      <section className="panel result-detail"><div><span className="eyebrow">Question review</span><h2>질문별 상세 피드백</h2><p>실제 평가 데이터가 연결되면 질문과 답변, 판단 근거를 이 영역에서 확인할 수 있습니다.</p></div><span className="status-pill status-soft">API 연결 예정</span></section>
      <div className="result-actions"><button className="button button-secondary" type="button" onClick={onRestart}><RefreshCcw size={17} /> 새 면접 시작하기</button></div>
    </AppShell>
  );
}
