import { ArrowRight, BarChart3, FileText, MessagesSquare } from "lucide-react";
import { AppShell } from "../components/AppShell";

interface StartScreenProps { onStart: () => void }

export function StartScreen({ onStart }: StartScreenProps) {
  return (
    <AppShell>
      <section className="start-hero">
        <div className="hero-keywords" aria-hidden="true">
          {["직무 요구사항", "경험 연결", "질문 5개", "답변 근거", "시선 피드백", "직무 적합성", "일관성", "모의 면접"].map((keyword, index) => (
            <span key={keyword} className={`hero-keyword hero-keyword-${index + 1}`}>{keyword}</span>
          ))}
        </div>
        <div className="start-copy">
          <span className="hero-kicker">AI INTERVIEW SIMULATOR</span>
          <h1>내 지원서류를 파고드는<br />맞춤 면접을 시작하세요</h1>
          <p>채용공고와 나의 경험을 연결한 다섯 개의 질문으로 연습하고, 답변 근거가 담긴 피드백을 확인할 수 있어요.</p>
          <button className="button button-primary start-button" type="button" onClick={onStart}>모의 면접 시작하기 <ArrowRight size={17} /></button>
        </div>
        <div className="start-steps">
          <article><span><FileText size={19} /></span><div><small>01</small><strong>서류 등록</strong><p>지원 정보와 경험을 입력합니다.</p></div></article>
          <article><span><MessagesSquare size={19} /></span><div><small>02</small><strong>질문 5개</strong><p>5초 준비 후 최대 90초간 답합니다.</p></div></article>
          <article><span><BarChart3 size={19} /></span><div><small>03</small><strong>근거 피드백</strong><p>태도와 직무 연결성을 확인합니다.</p></div></article>
        </div>
      </section>
    </AppShell>
  );
}
