import { Camera, Check, Eye, LockKeyhole, Mic, RefreshCcw, ScanFace } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "../components/AppShell";

interface DeviceCheckScreenProps { onComplete: () => void }

export function DeviceCheckScreen({ onComplete }: DeviceCheckScreenProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [checking, setChecking] = useState(true);
  const [cameraReady, setCameraReady] = useState(false);
  const [microphoneReady, setMicrophoneReady] = useState(false);
  const [error, setError] = useState("");

  const checkDevices = useCallback(async () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    setChecking(true);
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      setCameraReady(stream.getVideoTracks().length > 0);
      setMicrophoneReady(stream.getAudioTracks().length > 0);
    } catch {
      setCameraReady(false);
      setMicrophoneReady(false);
      setError("브라우저 설정에서 카메라와 마이크 권한을 허용한 뒤 다시 확인해 주세요.");
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void checkDevices();
    return () => streamRef.current?.getTracks().forEach((track) => track.stop());
  }, [checkDevices]);

  const ready = cameraReady && microphoneReady;
  return (
    <AppShell title="면접 전에 환경을 확인해 주세요" description="카메라와 마이크가 모두 정상일 때 면접을 시작할 수 있습니다.">
      <div className="device-layout">
        <section className="camera-preview">
          <video className="camera-video" ref={videoRef} autoPlay muted playsInline />
          <div className="camera-toolbar"><span><span className="live-dot" /> 미리보기</span><span>브라우저 내 처리</span></div>
          {!cameraReady && <div className="face-guide"><ScanFace size={52} strokeWidth={1.35} /><span>얼굴을 중앙에 맞춰주세요</span></div>}
          <div className="camera-badge"><Camera size={16} /> {cameraReady ? "카메라 연결됨" : "카메라 연결 대기"}</div>
        </section>
        <section className="panel device-panel">
          <div className="section-heading"><div><span className="eyebrow">Device check</span><h2>장치 상태</h2></div></div>
          <div className="device-list">
            <div className="device-item"><span className="device-icon"><Camera size={20} /></span><div><strong>카메라</strong><p>얼굴이 화면 중앙에 보이는지 확인합니다.</p></div><span className={`status-pill ${cameraReady ? "status-ready" : ""}`}>{cameraReady ? <><Check size={12} /> 정상</> : checking ? "확인 중" : "확인 필요"}</span></div>
            <div className="device-item"><span className="device-icon"><Mic size={20} /></span><div><strong>마이크</strong><p>답변을 녹음할 수 있는지 확인합니다.</p></div><span className={`status-pill ${microphoneReady ? "status-ready" : ""}`}>{microphoneReady ? <><Check size={12} /> 정상</> : checking ? "확인 중" : "확인 필요"}</span></div>
            <div className="device-item"><span className="device-icon"><Eye size={20} /></span><div><strong>시선 측정</strong><p>정면 유지 비율과 이탈 횟수만 계산합니다.</p></div><span className="status-pill status-soft">참고 지표</span></div>
          </div>
          <div className="interview-rules"><strong>면접 진행 안내</strong><span>질문 5개 · 준비 5초 · 질문당 최대 1분 30초</span><span>면접 중에는 점수나 피드백을 표시하지 않습니다.</span></div>
          <div className="privacy-box"><LockKeyhole size={18} /><p><strong>영상은 브라우저에서만 처리됩니다.</strong><span>영상 원본은 서버로 전송·저장되지 않으며 시선 값은 점수에 반영되지 않습니다.</span></p></div>
          {error && <p className="device-error">{error}</p>}
          {!ready && <button className="button button-secondary button-wide" type="button" onClick={() => void checkDevices()}><RefreshCcw size={16} /> 다시 확인</button>}
          <button className="button button-primary button-wide" type="button" disabled={!ready} onClick={onComplete}>면접 시작하기</button>
        </section>
      </div>
    </AppShell>
  );
}
