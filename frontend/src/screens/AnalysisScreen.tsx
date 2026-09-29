import { Check, FileSearch, ListChecks, Sparkles } from "lucide-react";
import { AppShell } from "../components/AppShell";

interface AnalysisScreenProps { onComplete: () => void; }

export function AnalysisScreen({ onComplete }: AnalysisScreenProps) {
  return (
    <AppShell title="맞춤 면접을 설계하고 있어요" description="등록한 자료에서 직무 요구사항과 주요 경험을 연결하고 있습니다.">
      <section className="process-card panel">
        <div className="process-visual"><span className="orbit orbit-one" /><span className="orbit orbit-two" /><Sparkles size={30} /></div>
        <div className="process-steps">
          <div className="process-step is-done"><span><Check size={17} /></span><div><strong>문서 읽기</strong><p>업로드한 자료에서 텍스트를 추출했습니다.</p></div></div>
          <div className="process-step is-active"><span><FileSearch size={17} /></span><div><strong>직무와 경험 연결</strong><p>강점과 확인이 필요한 경험을 찾고 있습니다.</p></div></div>
          <div className="process-step"><span><ListChecks size={17} /></span><div><strong>질문과 평가 기준 구성</strong><p>답변을 평가할 기준과 면접 순서를 준비합니다.</p></div></div>
        </div>
        <p className="process-note">실제 연동 전 확인을 위한 개발용 동작입니다.</p>
        <button className="button button-secondary" type="button" onClick={onComplete}>분석 완료 화면 확인</button>
      </section>
    </AppShell>
  );
}
