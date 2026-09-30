import { Camera, Clock3, Mic, Volume2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "../components/AppShell";
import { BrowserPerceptionController, type DeliveryMetrics } from "../perception";
import { BrowserAnswerRecorder } from "../recording";
import type { InterviewQuestion } from "../types/interview";

type InterviewPhase = "INITIALIZING" | "OPENING" | "READING" | "PREPARING" | "ANSWERING" | "TIMEOUT" | "SUBMITTING";

export interface CapturedAnswer {
  audio: Blob | null;
  duration_sec: number;
  timed_out: boolean;
  delivery_metrics: DeliveryMetrics;
}

const questionLabels: Record<InterviewQuestion["type"], string> = {
  INTRO: "자기소개",
  BEHAVIOR: "인성 질문",
  TECH: "기술 질문",
};

interface InterviewScreenProps {
  question: InterviewQuestion;
  current: number;
  total: number;
  onAnswerComplete: (answer: CapturedAnswer) => Promise<void> | void;
}

const formatTime = (seconds: number) => `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
const unavailableMetrics = (): DeliveryMetrics => ({ measurable: false, frontal_ratio: null, gaze_away_count: null });

export function InterviewScreen({ question, current, total, onAnswerComplete }: InterviewScreenProps) {
  const [phase, setPhase] = useState<InterviewPhase>("INITIALIZING");
  const [openingCountdown, setOpeningCountdown] = useState(5);
  const [countdown, setCountdown] = useState(5);
  const [remaining, setRemaining] = useState(90);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const perceptionRef = useRef<BrowserPerceptionController | null>(null);
  const recorderRef = useRef(new BrowserAnswerRecorder());
  const recordingStartedAt = useRef(0);
  const recordingPromise = useRef<ReturnType<BrowserAnswerRecorder["start"]> | null>(null);
  const finishingRef = useRef(false);
  const capturedRef = useRef<CapturedAnswer | null>(null);
  const progress = `${Math.round((current / total) * 100)}%`;

  useEffect(() => {
    let cancelled = false;
    const initialize = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (!videoRef.current) throw new Error("카메라 미리보기를 준비하지 못했습니다.");
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        try {
          const perception = new BrowserPerceptionController();
          perceptionRef.current = perception;
          await perception.initialize(videoRef.current);
          await perception.calibrate();
        } catch {
          perceptionRef.current?.dispose();
          perceptionRef.current = null;
          if (!cancelled) setWarning("시선 측정은 사용할 수 없지만 면접은 정상적으로 진행됩니다.");
        }
        if (!cancelled) setPhase(current === 1 ? "OPENING" : "READING");
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "카메라와 마이크를 준비하지 못했습니다.");
      }
    };
    void initialize();
    return () => {
      cancelled = true;
      recorderRef.current.cancel();
      perceptionRef.current?.dispose();
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, [current]);

  useEffect(() => {
    if (phase !== "OPENING") return;
    if (openingCountdown <= 0) {
      setPhase("READING");
      return;
    }
    const timer = window.setTimeout(() => setOpeningCountdown((value) => value - 1), 1_000);
    return () => window.clearTimeout(timer);
  }, [openingCountdown, phase]);

  useEffect(() => {
    if (phase !== "READING") return;
    let finished = false;
    const moveToPreparation = () => {
      if (finished) return;
      finished = true;
      setPhase("PREPARING");
    };
    // 정상 TTS를 자르지 않고, 브라우저가 종료 이벤트를 주지 않을 때만 안전하게 복구합니다.
    const fallback = window.setTimeout(moveToPreparation, 60_000);
    if ("speechSynthesis" in window) {
      const utterance = new SpeechSynthesisUtterance(question.text);
      utterance.lang = "ko-KR";
      utterance.onend = moveToPreparation;
      utterance.onerror = moveToPreparation;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    } else {
      moveToPreparation();
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
    const timer = window.setTimeout(() => setCountdown((value) => value - 1), 1_000);
    return () => window.clearTimeout(timer);
  }, [countdown, phase]);

  useEffect(() => {
    if (phase !== "ANSWERING" || !streamRef.current || recordingPromise.current) return;
    recordingStartedAt.current = performance.now();
    try {
      recordingPromise.current = recorderRef.current.start(streamRef.current);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "답변 녹음을 시작하지 못했습니다.");
      recordingPromise.current = Promise.resolve({ audio: null, reason: "microphone_disconnected" });
    }
    try {
      perceptionRef.current?.startAnswer();
    } catch {
      perceptionRef.current?.dispose();
      perceptionRef.current = null;
      setWarning("시선 측정은 사용할 수 없지만 답변은 계속 녹음됩니다.");
    }
  }, [phase]);

  const finishAnswer = useCallback(async (timedOut: boolean) => {
    if (finishingRef.current || !recordingPromise.current) return;
    finishingRef.current = true;
    setPhase(timedOut ? "TIMEOUT" : "SUBMITTING");
    try {
      if (!capturedRef.current) {
        const recorded = recorderRef.current.isRecording
          ? await recorderRef.current.stop(timedOut ? "time_limit" : "completed")
          : await recordingPromise.current;
        capturedRef.current = {
          audio: recorded.audio?.blob ?? null,
          duration_sec: Math.max(0, (performance.now() - recordingStartedAt.current) / 1_000),
          timed_out: timedOut,
          delivery_metrics: perceptionRef.current?.finishAnswer() ?? unavailableMetrics(),
        };
        if (timedOut) await new Promise((resolve) => window.setTimeout(resolve, 3_000));
      }
      await onAnswerComplete(capturedRef.current);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "답변을 처리하지 못했습니다.");
      finishingRef.current = false;
    }
  }, [onAnswerComplete]);

  useEffect(() => {
    if (phase !== "ANSWERING") return;
    const timer = window.setInterval(() => setRemaining((value) => Math.max(0, value - 1)), 1_000);
    return () => window.clearInterval(timer);
  }, [phase]);

  useEffect(() => {
    if (phase === "ANSWERING" && remaining === 0) void finishAnswer(true);
  }, [finishAnswer, phase, remaining]);

  const phaseLabel = phase === "INITIALIZING" ? "장치 준비 중" : phase === "OPENING" ? "면접 시작 전" : phase === "READING" ? "질문 읽는 중" : phase === "PREPARING" ? "답변 준비 중" : phase === "ANSWERING" ? "녹음 중" : phase === "TIMEOUT" ? "시간 종료" : "답변 전송 중";
  const showOpening = current === 1 && (phase === "INITIALIZING" || phase === "OPENING");

  return (
    <AppShell>
      <div className="interview-topbar">
        <div><span className="question-kind">{questionLabels[question.type]}</span><strong>질문 {current}</strong><span className="question-total">/ {total}</span></div>
        <div className="interview-progress" aria-label={`면접 진행률 ${progress}`}><span style={{ width: progress }} /></div>
        <span className={`recording-state phase-${phase.toLowerCase()}`}><span className="live-dot" /> {phaseLabel}</span>
      </div>
      <div className="interview-stage">
        <section className="question-card">
          {showOpening ? (
            <div className="interview-opening">
              <span>Interview begins shortly</span>
              <h1>면접이 곧 시작됩니다.</h1>
              <p>편안한 자세로 화면을 바라보고 첫 번째 질문을 준비해 주세요.</p>
              {phase === "OPENING" ? <div className="opening-countdown"><strong>{openingCountdown}</strong><span>초 후 첫 질문이 나옵니다</span></div> : <div className="opening-countdown is-loading"><span>카메라와 마이크를 준비하고 있습니다</span></div>}
            </div>
          ) : (
            <>
              <div className="question-audio"><Volume2 size={18} /><span>{phase === "INITIALIZING" ? "다음 질문을 준비하고 있습니다" : phase === "READING" ? "질문을 읽고 있습니다" : "질문 읽기가 끝났습니다"}</span></div>
              <h1>{question.text}</h1>
              {phase === "PREPARING" && <div className="preparation-count"><strong>{countdown}</strong><span>초 후 녹음을 시작합니다</span></div>}
              {(phase === "ANSWERING" || phase === "SUBMITTING") && <div className="answer-time"><Clock3 size={20} /><div><span>남은 시간</span><strong>{formatTime(remaining)}</strong></div></div>}
              {phase === "TIMEOUT" && <div className="timeout-message"><strong>답변 시간이 종료되었습니다.</strong><span>잠시 후 다음 질문으로 넘어갑니다.</span></div>}
              <p className="answer-guide">답변은 최대 1분 30초이며, 완료한 답변은 백그라운드에서 변환됩니다. 면접 중에는 평가나 피드백을 표시하지 않습니다.</p>
            </>
          )}
          {warning && <p className="device-warning">{warning}</p>}
          {error && <p className="device-error">{error}</p>}
          <button className="button button-primary answer-button" type="button" disabled={phase !== "ANSWERING"} onClick={() => void finishAnswer(false)}>{phase === "SUBMITTING" ? "답변 전송 중" : "답변 완료"}</button>
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
