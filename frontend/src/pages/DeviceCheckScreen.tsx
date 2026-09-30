import { Camera, Check, LockKeyhole, Mic, RefreshCcw, ScanFace } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "../components/AppShell";

interface DeviceCheckScreenProps { onComplete: () => void }

const MIC_RMS_THRESHOLD = 0.02;
const MIC_REQUIRED_FRAMES = 4;
const MIC_TEST_TIMEOUT_MS = 10_000;

export function DeviceCheckScreen({ onComplete }: DeviceCheckScreenProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analysisFrameRef = useRef<number | null>(null);
  const testTimeoutRef = useRef<number | null>(null);
  const checkSequenceRef = useRef(0);
  const [checking, setChecking] = useState(true);
  const [cameraReady, setCameraReady] = useState(false);
  const [microphoneConnected, setMicrophoneConnected] = useState(false);
  const [microphoneReady, setMicrophoneReady] = useState(false);
  const [microphoneTesting, setMicrophoneTesting] = useState(false);
  const [microphoneLevel, setMicrophoneLevel] = useState(0);
  const [error, setError] = useState("");

  const stopMicrophoneAnalysis = useCallback(() => {
    if (analysisFrameRef.current !== null) cancelAnimationFrame(analysisFrameRef.current);
    if (testTimeoutRef.current !== null) window.clearTimeout(testTimeoutRef.current);
    analysisFrameRef.current = null;
    testTimeoutRef.current = null;
    void audioContextRef.current?.close();
    audioContextRef.current = null;
  }, []);

  const releaseDevices = useCallback(() => {
    stopMicrophoneAnalysis();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, [stopMicrophoneAnalysis]);

  const startMicrophoneAnalysis = useCallback(async (stream: MediaStream) => {
    stopMicrophoneAnalysis();
    const AudioContextClass = window.AudioContext;
    const audioContext = new AudioContextClass();
    audioContextRef.current = audioContext;
    if (audioContext.state === "suspended") await audioContext.resume();

    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.25;
    audioContext.createMediaStreamSource(stream).connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    let loudFrames = 0;
    setMicrophoneTesting(true);

    const analyze = () => {
      analyser.getByteTimeDomainData(samples);
      let sumSquares = 0;
      for (const sample of samples) {
        const normalized = (sample - 128) / 128;
        sumSquares += normalized * normalized;
      }
      const rms = Math.sqrt(sumSquares / samples.length);
      setMicrophoneLevel(Math.min(100, Math.round((rms / 0.16) * 100)));
      loudFrames = rms >= MIC_RMS_THRESHOLD ? loudFrames + 1 : 0;

      if (loudFrames >= MIC_REQUIRED_FRAMES) {
        setMicrophoneReady(true);
        setMicrophoneTesting(false);
        setError("");
        stopMicrophoneAnalysis();
        return;
      }
      analysisFrameRef.current = requestAnimationFrame(analyze);
    };

    analysisFrameRef.current = requestAnimationFrame(analyze);
    testTimeoutRef.current = window.setTimeout(() => {
      if (analysisFrameRef.current !== null) cancelAnimationFrame(analysisFrameRef.current);
      analysisFrameRef.current = null;
      setMicrophoneTesting(false);
      setError("마이크 입력이 확인되지 않았습니다. 마이크에 대고 말한 뒤 다시 확인해 주세요.");
    }, MIC_TEST_TIMEOUT_MS);
  }, [stopMicrophoneAnalysis]);

  const checkDevices = useCallback(async () => {
    const checkSequence = ++checkSequenceRef.current;
    releaseDevices();
    setChecking(true);
    setCameraReady(false);
    setMicrophoneConnected(false);
    setMicrophoneReady(false);
    setMicrophoneTesting(false);
    setMicrophoneLevel(0);
    setError("");

    let stream: MediaStream | null = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      if (checkSequence !== checkSequenceRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const video = videoRef.current;
      if (!video) throw new Error("카메라 미리보기를 준비하지 못했습니다.");
      video.srcObject = stream;
      try {
        await video.play();
      } catch (cause) {
        // React 개발 모드의 중복 effect로 교체된 이전 재생 요청은 무시합니다.
        if (checkSequence !== checkSequenceRef.current) return;
        throw cause;
      }

      if (checkSequence !== checkSequenceRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }

      const cameraTrack = stream.getVideoTracks()[0];
      const microphoneTrack = stream.getAudioTracks()[0];
      setCameraReady(Boolean(cameraTrack && cameraTrack.readyState === "live" && video.videoWidth > 0));
      setMicrophoneConnected(Boolean(microphoneTrack && microphoneTrack.readyState === "live"));
      if (!microphoneTrack) throw new Error("사용 가능한 마이크가 없습니다.");
      await startMicrophoneAnalysis(stream);
    } catch (cause) {
      if (checkSequence !== checkSequenceRef.current) {
        stream?.getTracks().forEach((track) => track.stop());
        return;
      }
      releaseDevices();
      setCameraReady(false);
      setMicrophoneConnected(false);
      setMicrophoneReady(false);
      setError(cause instanceof Error ? cause.message : "브라우저 설정에서 카메라와 마이크 권한을 허용해 주세요.");
    } finally {
      setChecking(false);
    }
  }, [releaseDevices, startMicrophoneAnalysis]);

  useEffect(() => {
    void checkDevices();
    return () => {
      checkSequenceRef.current += 1;
      releaseDevices();
    };
  }, [checkDevices, releaseDevices]);

  const ready = cameraReady && microphoneReady;
  const microphoneStatus = microphoneReady ? "정상" : microphoneTesting ? "말해보세요" : checking ? "확인 중" : "확인 필요";

  return (
    <AppShell title="면접 전에 환경을 확인해 주세요" description="카메라 화면과 실제 마이크 입력이 모두 확인돼야 면접을 시작할 수 있습니다.">
      <div className="device-layout">
        <section className="camera-preview">
          <video className="camera-video" ref={videoRef} autoPlay muted playsInline />
          <div className="camera-toolbar"><span><span className="live-dot" /> 미리보기</span><span>브라우저 내 처리</span></div>
          {!cameraReady && <div className="face-guide"><ScanFace size={52} strokeWidth={1.35} /><span>얼굴을 중앙에 맞춰주세요</span></div>}
          <div className="camera-badge"><Camera size={16} /> {cameraReady ? "카메라 화면 확인됨" : "카메라 확인 대기"}</div>
        </section>
        <section className="panel device-panel">
          <div className="section-heading"><div><h2>장치 상태</h2></div></div>
          <div className="device-list">
            <div className="device-item"><span className="device-icon"><Camera size={20} /></span><div><strong>카메라</strong><p>실제 카메라 프레임이 재생되는지 확인합니다.</p></div><span className={`status-pill ${cameraReady ? "status-ready" : ""}`}>{cameraReady ? <><Check size={12} /> 정상</> : checking ? "확인 중" : "확인 필요"}</span></div>
            <div className="device-item"><span className="device-icon"><Mic size={20} /></span><div><strong>마이크</strong><p>{microphoneReady ? "실제 음성 입력을 확인했습니다." : microphoneConnected ? "마이크에 대고 짧게 말해보세요." : "마이크 연결과 권한을 확인합니다."}</p><div className="microphone-meter" aria-label={`마이크 입력 ${microphoneLevel}%`}><span style={{ width: `${microphoneLevel}%` }} /></div></div><span className={`status-pill ${microphoneReady ? "status-ready" : ""}`}>{microphoneReady && <Check size={12} />}{microphoneStatus}</span></div>
          </div>
          <div className="interview-rules"><strong>면접 진행 안내</strong><span>질문 5개 · 준비 5초 · 질문당 최대 1분 30초</span><span>면접 중에는 점수나 피드백을 표시하지 않습니다.</span></div>
          <div className="privacy-box"><LockKeyhole size={18} /><p><strong>영상과 마이크 확인은 브라우저에서 처리됩니다.</strong><span>영상 원본은 서버로 전송·저장되지 않으며 시선 값은 점수에 반영되지 않습니다.</span></p></div>
          {error && <p className="device-error">{error}</p>}
          {!ready && <button className="button button-secondary button-wide" type="button" onClick={() => void checkDevices()}><RefreshCcw size={16} /> 다시 확인</button>}
          <button className="button button-primary button-wide" type="button" disabled={!ready} onClick={onComplete}>면접 시작하기</button>
        </section>
      </div>
    </AppShell>
  );
}
