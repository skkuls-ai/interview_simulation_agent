import { BriefcaseBusiness, Check, FileText, ScrollText, UploadCloud } from "lucide-react";
import { useState, type ChangeEvent, type ReactNode } from "react";
import { AppShell } from "../components/AppShell";
import type { DocumentInput, SessionSetup } from "../types/interview";

interface SetupScreenProps { onSubmit: (setup: SessionSetup) => void }
type InputMode = "file" | "text";

interface DocumentFieldProps {
  title: string;
  description: string;
  icon: ReactNode;
  value: DocumentInput;
  onChange: (value: DocumentInput) => void;
}

const emptyDocument = (): DocumentInput => ({ file: null, text: "" });
const isFilled = (value: DocumentInput) => Boolean(value.file || value.text.trim());

function DocumentField({ title, description, icon, value, onChange }: DocumentFieldProps) {
  const [mode, setMode] = useState<InputMode>("file");
  const pickFile = (event: ChangeEvent<HTMLInputElement>) => onChange({ file: event.target.files?.[0] ?? null, text: "" });

  return (
    <section className={`document-card${isFilled(value) ? " is-selected" : ""}`}>
      <header className="document-card-header">
        <span className="upload-icon">{isFilled(value) ? <Check size={20} /> : icon}</span>
        <div><strong>{title}</strong><p>{description}</p></div>
        <div className="input-tabs" role="tablist" aria-label={`${title} 입력 방식`}>
          <button className={mode === "file" ? "is-active" : ""} type="button" onClick={() => setMode("file")}>파일</button>
          <button className={mode === "text" ? "is-active" : ""} type="button" onClick={() => setMode("text")}>직접 입력</button>
        </div>
      </header>
      {mode === "file" ? (
        <label className="document-file">
          <span>{value.file?.name ?? "PDF, DOCX, TXT · 최대 10MB"}</span>
          <strong><UploadCloud size={16} /> {value.file ? "변경" : "파일 선택"}</strong>
          <input type="file" accept=".pdf,.docx,.txt" onChange={pickFile} />
        </label>
      ) : (
        <textarea
          className="document-textarea"
          rows={5}
          value={value.text}
          onChange={(event) => onChange({ file: null, text: event.target.value })}
          placeholder={`${title} 내용을 붙여 넣어 주세요.`}
        />
      )}
    </section>
  );
}

export function SetupScreen({ onSubmit }: SetupScreenProps) {
  const [privacyConsent, setPrivacyConsent] = useState(false);
  const [resume, setResume] = useState(emptyDocument);
  const [jobPosting, setJobPosting] = useState(emptyDocument);
  const [jobDescription, setJobDescription] = useState(emptyDocument);
  const [coverLetter, setCoverLetter] = useState(emptyDocument);
  const ready = privacyConsent && [resume, jobPosting, jobDescription, coverLetter].every(isFilled);

  return (
    <AppShell title="면접에 사용할 서류를 등록해 주세요" description="네 가지 자료를 바탕으로 지원 직무와 경험을 연결하고, 면접용 질문을 준비합니다.">
      <div className="upload-layout">
        <section className="panel setup-panel">
          <div className="section-heading"><div><span className="eyebrow">Required documents</span><h2>필수 파일 업로드</h2></div><span className="section-count">필수 4개</span></div>
          <div className="document-list">
            <DocumentField title="이력서" description= "" icon={<FileText size={20} />} value={resume} onChange={setResume} />
            <DocumentField title="채용공고" description="" icon={<BriefcaseBusiness size={20} />} value={jobPosting} onChange={setJobPosting} />
            <DocumentField title="직무기술서" description="" icon={<BriefcaseBusiness size={20} />} value={jobDescription} onChange={setJobDescription} />
            <DocumentField title="자기소개서" description="" icon={<ScrollText size={20} />} value={coverLetter} onChange={setCoverLetter} />
          </div>
          <label className="consent-row">
            <input type="checkbox" checked={privacyConsent} onChange={(event) => setPrivacyConsent(event.target.checked)} />
            <span><strong>면접 진행 및 데이터 처리 안내에 동의합니다.</strong><small>녹음은 STT 변환 후 삭제되며, 카메라 영상은 서버로 전송하거나 저장하지 않습니다.</small></span>
          </label>
          <button className="button button-primary button-wide" type="button" disabled={!ready} onClick={() => onSubmit({ privacyConsent, resume, jobPosting, jobDescription, coverLetter })}>AI 분석 시작하기</button>
        </section>
        <aside className="setup-aside">
          <span className="aside-kicker">Before you begin</span>
          <h2>등록 전에 확인해 주세요</h2>
          <ol className="guide-list">
            <li><span>01</span><div><strong>모든 자료는 필수예요</strong><p>파일 또는 텍스트 중 편한 방식으로 입력할 수 있습니다.</p></div></li>
            <li><span>02</span><div><strong>질문은 미리 준비돼요</strong><p>면접 중에는 질문과 평가 기준이 바뀌지 않습니다.</p></div></li>
            <li><span>03</span><div><strong>원본 영상은 저장하지 않아요</strong><p>카메라에서는 참고용 시선 지표만 계산합니다.</p></div></li>
          </ol>
        </aside>
      </div>
    </AppShell>
  );
}
