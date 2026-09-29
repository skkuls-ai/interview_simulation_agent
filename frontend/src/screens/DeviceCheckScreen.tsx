import { Camera, Eye, LockKeyhole, Mic, ScanFace } from "lucide-react";
import { AppShell } from "../components/AppShell";

interface DeviceCheckScreenProps { onComplete: () => void; }

export function DeviceCheckScreen({ onComplete }: DeviceCheckScreenProps) {
  return (
    <AppShell title="화면과 소리를 확인해 주세요" description="얼굴이 가이드 안에 들어오도록 앉고, 마이크에 짧게 말해보세요.">
      <div className="device-layout">
        <section className="camera-preview">
          <div className="camera-toolbar"><span><span className="live-dot" /> 미리보기</span><span>16:9</span></div>
          <div className="face-guide"><ScanFace size={52} strokeWidth={1.35} /><span>얼굴을 중앙에 맞춰주세요</span></div>
          <div className="camera-badge"><Camera size={16} /> 카메라 연결 대기</div>
        </section>
        <section className="panel device-panel">
          <div className="section-heading"><div><span className="eyebrow">Device check</span><h2>장치 상태</h2></div></div>
          <div className="device-list">
            <div className="device-item"><span className="device-icon"><Camera size={20} /></span><div><strong>카메라</strong><p>얼굴 인식 상태를 확인합니다.</p></div><span className="status-pill">대기</span></div>
            <div className="device-item"><span className="device-icon"><Mic size={20} /></span><div><strong>마이크</strong><p>음성 입력 수준을 확인합니다.</p></div><span className="status-pill">대기</span></div>
            <div className="device-item"><span className="device-icon"><Eye size={20} /></span><div><strong>시선 분석</strong><p>카메라 방향 유지 비율을 측정합니다.</p></div><span className="status-pill status-soft">안내</span></div>
          </div>
          <div className="privacy-box"><LockKeyhole size={18} /><p><strong>영상은 브라우저에서만 처리됩니다.</strong><span>서버에는 분석된 시선·표정 지표만 전송합니다.</span></p></div>
          <button className="button button-primary button-wide" type="button" onClick={onComplete}>점검 완료하고 시작하기</button>
        </section>
      </div>
    </AppShell>
  );
}
