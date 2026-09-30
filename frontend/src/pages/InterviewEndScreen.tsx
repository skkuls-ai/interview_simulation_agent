import { useEffect, useRef } from "react";

interface InterviewEndScreenProps { onComplete: () => void }

const DISPLAY_MS = 5_000;

export function InterviewEndScreen({ onComplete }: InterviewEndScreenProps) {
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    const timer = window.setTimeout(() => onCompleteRef.current(), DISPLAY_MS);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="end-screen" role="status" aria-live="polite">
      <span className="end-blob end-blob-a" />
      <span className="end-blob end-blob-b" />
      <span className="end-blob end-blob-c" />
      <div className="end-content">
        <svg className="end-check" viewBox="0 0 96 96" aria-hidden="true">
          <circle className="end-ring" cx="48" cy="48" r="44" />
          <path className="end-tick" d="M30 50 L43 63 L67 36" />
        </svg>
        <h1>수고하셨습니다.</h1>
        <p>면접이 종료되었습니다.</p>
        <small>잠시 후 결과 분석이 시작됩니다.</small>
      </div>
      <div className="end-progress"><span /></div>
    </div>
  );
}
