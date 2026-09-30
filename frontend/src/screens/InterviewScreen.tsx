import { Camera, Clock3, Mic, Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AppShell } from "../components/AppShell";
import type { InterviewQuestion } from "../types/interview";

type InterviewPhase = "READING" | "PREPARING" | "ANSWERING" | "TIMEOUT" | "SUBMITTING";

const questionLabels: Record<InterviewQuestion["type"], string> = {
  INTRO: "자기소개",
  BEHAVIOR: "인성 질문",
  TECH: "기술 질문",
};

interface InterviewScreenProps {
  question: InterviewQuestion;
  current: number;
  total: number;
  onAnswerComplete: () => void;
}

const formatTime = (seconds: number) => `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;

export function InterviewScreen({ question, current, total, onAnswerComplete }: InterviewScreenProps) {
  const [phase, setPhase] = useState<InterviewPhase>("READING");
  const [countdown, setCountdown] = useState(5);
  const [remaining, setRemaining] = useState(90);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const progress = `${Math.round((current / total) * 100)}%`;

  useEffect(() => {
    void navigator.mediaDevices.getUserMedia({ video: true, audio: true }).then((stream) => {
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
    }).catch(() => undefined);
    return () => streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  useEffect(() => {
    if (phase !== "READING") return;
    let finished = false;
    const moveToPreparation = () => {
      if (finished) return;
      finished = true;
      setPhase("PREPARING");
    };
    const fallback = window.setTimeout(moveToPreparation, 2400);
    if ("speechSynthesis" in window) {
      const utterance = new SpeechSynthesisUtterance(question.text);
      utterance.lang = "ko-KR";
      utterance.onend = moveToPreparation;
      utterance.onerror = moveToPreparation;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    }
    return () => {
      finished = true;
      window.clearTimeout(fallback);
      window.speechSynthesis?.cancel();
    };
  }, [phase, question.text]);

  useEffect(() => {
    if (phase !== "PREPARING") return;
    if (countdown <= 0) {
      setPhase("ANSWERING");
      return;
    }
    const timer = window.setTimeout(() => setCountdown((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [countdown, phase]);

  useEffect(() => {
    if (phase !== "ANSWERING") return;
    const timer = window.setInterval(() => {
      setRemaining((value) => {
        if (value <= 1) {
          window.clearInterval(timer);
          setPhase("TIMEOUT");
          return 0;
        }
        return value - 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [phase]);

  useEffect(() => {
    if (phase !== "TIMEOUT" && phase !== "SUBMITTING") return;
    const timer = window.setTimeout(onAnswerComplete, phase === "TIMEOUT" ? 3000 : 550);
    return () => window.clearTimeout(timer);
  }, [onAnswerComplete, phase]);

  const phaseLabel = phase === "READING" ? "질문 읽는 중" : phase === "PREPARING" ? "준비 중" : phase === "ANSWERING" ? "녹음 중" : phase === "TIMEOUT" ? "시간 종료" : "답변 전송 중";

  return (
    <AppShell>
      <div className="interview-topbar">
        <div><span className="question-kind">{questionLabels[question.type]}</span><strong>질문 {current}</strong><span className="question-total">/ {total}</span></div>
        <div className="interview-progress" aria-label={`면접 진행률 ${progress}`}><span style={{ width: progress }} /></div>
        <span className={`recording-state phase-${phase.toLowerCase()}`}><span className="live-dot" /> {phaseLabel}</span>
      </div>
      <div className="interview-stage">
        <section className="question-card">
          <div className="question-audio"><Volume2 size={18} /><span>{phase === "READING" ? "질문을 읽고 있습니다" : "질문 읽기가 끝났습니다"}</span></div>
          <h1>{question.text}</h1>
          {phase === "PREPARING" && <div className="preparation-count"><strong>{countdown}</strong><span>초 후 녹음을 시작합니다</span></div>}
          {(phase === "ANSWERING" || phase === "SUBMITTING") && <div className="answer-time"><Clock3 size={20} /><div><span>남은 시간</span><strong>{formatTime(remaining)}</strong></div></div>}
          {phase === "TIMEOUT" && <div className="timeout-message"><strong>답변 시간이 종료되었습니다.</strong><span>잠시 후 다음 질문으로 넘어갑니다.</span></div>}
          <p className="answer-guide">답변은 최대 1분 30초이며, 완료한 답변은 백그라운드에서 변환됩니다. 면접 중에는 평가나 피드백을 표시하지 않습니다.</p>
          <button className="button button-primary answer-button" type="button" disabled={phase !== "ANSWERING"} onClick={() => setPhase("SUBMITTING")}>{phase === "SUBMITTING" ? "답변 전송 중" : "답변 완료"}</button>
        </section>
        <aside className="camera-preview interview-camera">
          <video className="camera-video" ref={videoRef} autoPlay muted playsInline />
          <div className="camera-toolbar"><span><span className="live-dot" /> Camera</span><span>본인 화면</span></div>
          <div className="media-controls"><span><Mic size={18} /></span><span><Camera size={18} /></span></div>
        </aside>
      </div>
    </AppShell>
  );
}
