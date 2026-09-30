import { ChevronDown, Eye, FileCheck2, MessageSquareQuote, RefreshCcw, RotateCcw, Timer } from "lucide-react";
import { AppShell } from "../components/AppShell";
import type { InterviewResult } from "../types/interview";

interface ResultScreenProps {
  result: InterviewResult;
  onRetry: () => void;
  onRestart: () => void;
}

export function ResultScreen({ result, onRetry, onRestart }: ResultScreenProps) {
  return (
    <AppShell>
      <section className="result-hero">
        <span className="result-icon"><FileCheck2 size={25} /></span>
        <div><span className="eyebrow">Interview feedback</span><h1>면접 피드백</h1><p>{result.summary}</p></div>
        <div className="result-score"><span>완료한 질문</span><strong>5</strong><small>questions</small></div>
      </section>

      <section className="panel report-section">
        <header className="report-heading"><div><span className="eyebrow">Attitude</span><h2>태도와 전달 방식</h2></div><span className="reference-badge">참고 지표 · 점수 미반영</span></header>
        <div className="metric-grid">
          <article><Eye size={18} /><span>정면 유지 비율</span><strong>{result.attitude.frontal_ratio === null ? "측정 불가" : `${Math.round(result.attitude.frontal_ratio * 100)}%`}</strong></article>
          <article><MessageSquareQuote size={18} /><span>시선 이탈</span><strong>{result.attitude.gaze_away_count === null ? "측정 불가" : `${result.attitude.gaze_away_count}회`}</strong></article>
          <article><Timer size={18} /><span>시간 초과</span><strong>{result.attitude.timed_out_count}회</strong></article>
        </div>
        <ul className="advice-list">{result.attitude.advice.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>

      <div className="result-grid">
        <section className="panel verdict-card">
          <header><div><span className="eyebrow">Job fit</span><h2>직무 적합성</h2></div><span className="verdict">{result.job_fit.verdict}</span></header>
          <p>{result.job_fit.reason}</p><blockquote>“{result.job_fit.quote}”</blockquote>
        </section>
        <section className="panel verdict-card">
          <header><div><span className="eyebrow">Consistency</span><h2>답변 일관성</h2></div><span className="verdict">{result.consistency.verdict}</span></header>
          <p>{result.consistency.reason}</p><blockquote>“{result.consistency.quote}”</blockquote>
        </section>
      </div>

      <section className="question-review">
        <div className="section-heading"><div><span className="eyebrow">Question review</span><h2>질문별 상세 피드백</h2></div></div>
        {result.per_question.map((item, index) => (
          <details className="panel review-item" key={item.question_id} open={index === 0}>
            <summary><span>{item.question_id}</span><strong>{item.question}</strong><ChevronDown size={18} /></summary>
            <div className="review-body">
              <div><small>내 답변</small><p>{item.answer ?? "답변이 기록되지 않았습니다."}</p></div>
              <div className="review-columns"><article><small>잘한 점</small><ul>{item.strengths.map((text) => <li key={text}>{text}</li>)}</ul></article><article><small>보완할 점</small><ul>{item.gaps.map((text) => <li key={text}>{text}</li>)}</ul></article></div>
              <div className="next-action"><small>다음 연습</small><strong>{item.next_action}</strong></div>
            </div>
          </details>
        ))}
      </section>

      <div className="result-actions">
        <button className="button button-secondary" type="button" onClick={onRestart}><RotateCcw size={17} /> 처음으로</button>
        <button className="button button-primary" type="button" onClick={onRetry}><RefreshCcw size={17} /> 같은 서류로 다시 연습하기</button>
      </div>
    </AppShell>
  );
}
