import { ChevronDown, Eye, FileCheck2, Gauge, MessageCircle, RefreshCcw, RotateCcw, ScanFace, Timer } from "lucide-react";
import { AppShell } from "../components/AppShell";
import type { InterviewResult, QuestionFeedback } from "../types/interview";

interface ResultScreenProps {
  result: InterviewResult;
  onRetry: () => void;
  onRestart: () => void;
}

type Fit = InterviewResult["job_fit"];

function VerdictCard({ title, fit, evidenceLabel }: { title: string; fit: Fit; evidenceLabel: string }) {
  const quotes = fit.quotes?.length ? fit.quotes : fit.quote ? [fit.quote] : [];
  return (
    <section className="panel verdict-card">
      <header><div><h2>{title}</h2></div><span className="verdict">{fit.verdict}</span></header>
      <p>{fit.reason}</p>
      {quotes.map((text) => <blockquote key={text}>“{text}”</blockquote>)}
      {fit.evidence && fit.evidence.length > 0 && (
        <div className="evidence-list">
          <small>{evidenceLabel}</small>
          <ul>{fit.evidence.map((text) => <li key={text}>{text}</li>)}</ul>
        </div>
      )}
    </section>
  );
}

function answerTime(item: QuestionFeedback): string | null {
  if (item.duration_sec === undefined) return null;
  const sec = `${Math.round(item.duration_sec)}초`;
  return item.timed_out ? `${sec} · 시간 초과` : sec;
}

export function ResultScreen({ result, onRetry, onRestart }: ResultScreenProps) {
  const { attitude } = result;
  const speechValue = (value: number | null | undefined, unit: string) =>
    value === null || value === undefined ? "측정 불가" : `${value}${unit}`;
  return (
    <AppShell>
      <section className="result-hero">
        <span className="result-icon"><FileCheck2 size={25} /></span>
        <div><h1>면접 피드백</h1><p>{result.summary}</p></div>
      </section>

      <section className="panel report-section">
        <header className="report-heading"><div><h2>태도와 전달 방식</h2></div></header>
        <div className="metric-grid">
          <article><ScanFace size={18} /><span>정면 유지 비율</span><strong>{attitude.frontal_ratio === null ? "측정 불가" : `${Math.round(attitude.frontal_ratio * 100)}%`}</strong></article>
          <article><Eye size={18} /><span>시선 이탈</span><strong>{attitude.gaze_away_count === null ? "측정 불가" : `${attitude.gaze_away_count}회`}</strong></article>
          <article><Timer size={18} /><span>시간 초과</span><strong>{attitude.timed_out_count}회</strong></article>
          {attitude.words_per_min !== undefined && (
            <article><Gauge size={18} /><span>말 속도 (분당 어절)</span><strong>{speechValue(attitude.words_per_min, "")}</strong></article>
          )}
          {attitude.filler_count !== undefined && (
            <article><MessageCircle size={18} /><span>군말</span><strong>{speechValue(attitude.filler_count, "회")}</strong></article>
          )}
        </div>
        <ul className="advice-list">{attitude.advice.map((item) => <li key={item}>{item}</li>)}</ul>
        {attitude.quotes && attitude.quotes.length > 0 && (
          <div className="attitude-quotes">
            <small>말투 근거</small>
            {attitude.quotes.map((q) => <blockquote key={`${q.question_id}-${q.text}`}><span>{q.question_id}</span>“{q.text}”</blockquote>)}
          </div>
        )}
      </section>

      <div className="result-grid">
        <VerdictCard title="직무 적합성" fit={result.job_fit} evidenceLabel="근거 요구사항" />
        <VerdictCard title="답변 일관성" fit={result.consistency} evidenceLabel="비교한 서류 주장" />
      </div>

      <section className="question-review">
        <div className="section-heading"><div><h2>질문별 상세 피드백</h2></div></div>
        {result.per_question.map((item, index) => {
          const time = answerTime(item);
          const claims = item.linked_claims ?? [];
          const checkpoints = item.linked_checkpoints ?? [];
          return (
            <details className="panel review-item" key={item.question_id} open={index === 0}>
              <summary><span>{item.question_id}</span><strong>{item.question}</strong><ChevronDown size={18} /></summary>
              <div className="review-body">
                <div><small>내 답변{time ? ` · ${time}` : ""}</small><p>{item.answer ?? "답변이 기록되지 않았습니다."}</p></div>
                <div className="review-columns"><article><small>잘한 점</small><ul>{item.strengths.map((text) => <li key={text}>{text}</li>)}</ul></article><article><small>보완할 점</small><ul>{item.gaps.map((text) => <li key={text}>{text}</li>)}</ul></article></div>
                <div className="next-action"><small>다음 연습</small><strong>{item.next_action}</strong></div>
                {(claims.length > 0 || checkpoints.length > 0) && (
                  <div className="linked-info">
                    {claims.length > 0 && <article><small>연결된 서류 주장</small><ul>{claims.map((text) => <li key={text}>{text}</li>)}</ul></article>}
                    {checkpoints.length > 0 && <article><small>확인 포인트</small><ul>{checkpoints.map((text) => <li key={text}>{text}</li>)}</ul></article>}
                  </div>
                )}
              </div>
            </details>
          );
        })}
      </section>

      <div className="result-actions">
        <button className="button button-secondary" type="button" onClick={onRestart}><RotateCcw size={17} /> 처음으로</button>
        <button className="button button-primary" type="button" onClick={onRetry}><RefreshCcw size={17} /> 같은 서류로 다시 연습하기</button>
      </div>
    </AppShell>
  );
}
