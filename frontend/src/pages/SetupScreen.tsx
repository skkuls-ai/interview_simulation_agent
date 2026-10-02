import { BriefcaseBusiness, Check, FileText, ScrollText, UploadCloud } from "lucide-react";
import { useEffect, useState, type ChangeEvent, type ReactNode } from "react";
import { AppShell } from "../components/AppShell";
import { ApiError } from "../api/client";
import type { DocumentInput, SessionSetup } from "../types/interview";

interface SetupScreenProps { onSubmit: (setup: SessionSetup) => Promise<void> | void }
type InputMode = "file" | "text";
type DocumentKey = "resume" | "job_posting" | "job_description" | "cover_letter";

interface DocumentFieldProps {
  title: string;
  description: string;
  icon: ReactNode;
  value: DocumentInput;
  onChange: (value: DocumentInput) => void;
  error?: string;
  textModeRequest?: number;
}

const emptyDocument = (): DocumentInput => ({ file: null, text: "" });
const isFilled = (value: DocumentInput) => Boolean(value.file || value.text.trim());
const isDocumentKey = (field: string | undefined): field is DocumentKey =>
  field === "resume" || field === "job_posting" || field === "job_description" || field === "cover_letter";

function DocumentField({ title, description, icon, value, onChange, error, textModeRequest = 0 }: DocumentFieldProps) {
  const [mode, setMode] = useState<InputMode>("file");
  const pickFile = (event: ChangeEvent<HTMLInputElement>) => onChange({ file: event.target.files?.[0] ?? null, text: "" });

  useEffect(() => {
    if (textModeRequest > 0) setMode("text");
  }, [textModeRequest]);

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
      {error && <p className="document-error" role="alert">{error}</p>}
    </section>
  );
}

export function SetupScreen({ onSubmit }: SetupScreenProps) {
  const [privacyConsent, setPrivacyConsent] = useState(false);
  const [resume, setResume] = useState(emptyDocument);
  const [jobPosting, setJobPosting] = useState(emptyDocument);
  const [jobDescription, setJobDescription] = useState(emptyDocument);
  const [coverLetter, setCoverLetter] = useState(emptyDocument);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<DocumentKey, string>>>({});
  const [textModeRequests, setTextModeRequests] = useState<Partial<Record<DocumentKey, number>>>({});
  const ready = privacyConsent && [resume, jobPosting, jobDescription, coverLetter].every(isFilled);

  const setters: Record<DocumentKey, (value: DocumentInput) => void> = {
    resume: setResume,
    job_posting: setJobPosting,
    job_description: setJobDescription,
    cover_letter: setCoverLetter,
  };

  const submit = async () => {
    setSubmitting(true);
    setFormError("");
    setFieldErrors({});
    try {
      await onSubmit({ privacyConsent, resume, jobPosting, jobDescription, coverLetter });
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "서류를 제출하지 못했습니다.";
      const field = cause instanceof ApiError ? cause.field : undefined;
      const code = cause instanceof ApiError ? cause.code : undefined;
      if (isDocumentKey(field)) {
        setFieldErrors({ [field]: message });
        if (code === "TEXT_EXTRACTION_FAILED") {
          setters[field](emptyDocument());
          setTextModeRequests((current) => ({ ...current, [field]: (current[field] ?? 0) + 1 }));
        }
      } else {
        setFormError(message);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppShell title="면접에 사용할 서류를 등록해 주세요" description="네 가지 자료를 바탕으로 지원 직무와 경험을 연결하고, 면접용 질문을 준비합니다.">
      <div className="upload-layout">
        <section className="panel setup-panel">
          <div className="section-heading"><div><h2>필수 파일 업로드</h2></div><span className="section-count">필수 4개</span></div>
          <div className="document-list">
            <DocumentField title="이력서" description= "" icon={<FileText size={20} />} value={resume} onChange={setResume} error={fieldErrors.resume} textModeRequest={textModeRequests.resume} />
            <DocumentField title="채용공고" description="" icon={<BriefcaseBusiness size={20} />} value={jobPosting} onChange={setJobPosting} error={fieldErrors.job_posting} textModeRequest={textModeRequests.job_posting} />
            <DocumentField title="직무기술서" description="" icon={<BriefcaseBusiness size={20} />} value={jobDescription} onChange={setJobDescription} error={fieldErrors.job_description} textModeRequest={textModeRequests.job_description} />
            <DocumentField title="자기소개서" description="" icon={<ScrollText size={20} />} value={coverLetter} onChange={setCoverLetter} error={fieldErrors.cover_letter} textModeRequest={textModeRequests.cover_letter} />
          </div>
          <label className="consent-row">
            <input type="checkbox" checked={privacyConsent} onChange={(event) => setPrivacyConsent(event.target.checked)} />
            <span><strong>면접 진행 및 데이터 처리 안내에 동의합니다.</strong><small>녹음은 STT 변환 후 삭제되며, 카메라 영상은 서버로 전송하거나 저장하지 않습니다.</small></span>
          </label>
          {formError && <p className="document-error" role="alert">{formError}</p>}
          <button className="button button-primary button-wide" type="button" disabled={!ready || submitting} onClick={() => void submit()}>{submitting ? "서류 전송 중" : "AI 분석 시작하기"}</button>
        </section>
        <aside className="setup-aside">
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
