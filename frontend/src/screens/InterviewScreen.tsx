import { Camera, Clock3, Mic, Volume2 } from "lucide-react";
import { AppShell } from "../components/AppShell";
import type { InterviewPrompt } from "../types/interview";

const promptLabels: Record<InterviewPrompt["type"], string> = {
  SELF_INTRO: "자기소개", MAIN_QUESTION: "본 질문", FOLLOW_UP: "꼬리질문", CLOSING: "마무리 질문", NO_RESPONSE_CONFIRM: "응답 확인",
};

interface InterviewScreenProps { prompt: InterviewPrompt; current: number; total: number; onAnswerComplete: () => void; }

export function InterviewScreen({ prompt, current, total, onAnswerComplete }: InterviewScreenProps) {
  const progress = `${Math.round((current / total) * 100)}%`;
  return (
    <AppShell>
      <div className="interview-topbar">
        <div><span className="question-kind">{promptLabels[prompt.type]}</span><strong>질문 {current}</strong><span className="question-total">/ {total}</span></div>
        <div className="interview-progress" aria-label={`면접 진행률 ${progress}`}><span style={{ width: progress }} /></div>
        <span className="recording-state"><span className="live-dot" /> 답변 중</span>
      </div>
      <div className="interview-stage">
        <section className="question-card">
          <div className="question-audio"><Volume2 size={18} /><span>질문 음성이 재생되었습니다</span></div>
          <h1>{prompt.text}</h1>
          <div className="answer-time"><Clock3 size={20} /><div><span>답변 시간</span><strong>00:42</strong></div></div>
          <p className="answer-guide">{prompt.preparationSeconds}초의 준비시간 후 녹음이 시작됩니다. {prompt.softLimitSeconds}초가 지나면 초과 시간을 표시하지만 답변은 끊지 않습니다.</p>
          <button className="button button-primary answer-button" type="button" onClick={onAnswerComplete}>답변 완료</button>
        </section>
        <aside className="camera-preview interview-camera">
          <div className="camera-toolbar"><span><span className="live-dot" /> Camera</span><span>본인 화면</span></div>
          <div className="face-guide compact"><Camera size={42} strokeWidth={1.35} /><span>카메라 미리보기</span></div>
          <div className="media-controls"><span><Mic size={18} /></span><span><Camera size={18} /></span></div>
        </aside>
      </div>
    </AppShell>
  );
}
