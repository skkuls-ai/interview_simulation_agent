import { BriefcaseBusiness, Check, FileText, ScrollText, UploadCloud } from "lucide-react";
import { useState, type ChangeEvent, type ReactNode } from "react";
import { AppShell } from "../components/AppShell";
import type { SessionSetup } from "../types/interview";

interface SetupScreenProps {
  onSubmit: (setup: SessionSetup) => void;
}

interface FileFieldProps {
  title: string;
  description: string;
  icon: ReactNode;
  value: File | null;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
}

const heroKeywords = [
  "JD 분석", "경험 연결", "직무 맞춤 질문", "실전형 꼬리질문",
  "답변 분석", "역량별 피드백", "모의 면접", "종합 리포트",
];

function FileField({ title, description, icon, value, onChange }: FileFieldProps) {
  return (
    <label className={`upload-card${value ? " is-selected" : ""}`}>
      <span className="upload-icon">{value ? <Check size={22} /> : icon}</span>
      <span className="upload-copy">
        <strong>{title} <small>선택</small></strong>
        <span>{value?.name ?? description}</span>
      </span>
      <span className="upload-action"><UploadCloud size={18} /> {value ? "변경" : "파일 선택"}</span>
      <input type="file" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg" onChange={onChange} />
    </label>
  );
}

export function SetupScreen({ onSubmit }: SetupScreenProps) {
  const [consented, setConsented] = useState(false);
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [coverLetterFile, setCoverLetterFile] = useState<File | null>(null);

  const file = (setter: (value: File | null) => void) =>
    (event: ChangeEvent<HTMLInputElement>) => setter(event.target.files?.[0] ?? null);

  return (
    <AppShell
      title="나에게 맞춘 면접을 준비해볼까요?"
      description="자료를 등록하면 경험과 지원 직무를 반영해 질문을 구성합니다. 자료 없이도 시작할 수 있어요."
    >
      <div className="hero-keywords" aria-hidden="true">
        {heroKeywords.map((keyword, index) => <span key={keyword} className={`hero-keyword hero-keyword-${index + 1}`}>{keyword}</span>)}
      </div>
      <div className="setup-layout" id="setup-materials">
        <section className="panel setup-panel">
          <div className="section-heading">
            <div><span className="eyebrow">선택 사항</span><h2>개인화 자료</h2></div>
            <span className="section-count">최대 3개</span>
          </div>
          <div className="upload-list">
            <FileField title="채용공고" description="지원 직무의 JD를 등록해 주세요" icon={<BriefcaseBusiness size={22} />} value={jdFile} onChange={file(setJdFile)} />
            <FileField title="이력서" description="PDF, DOCX, TXT 또는 이미지" icon={<FileText size={22} />} value={resumeFile} onChange={file(setResumeFile)} />
            <FileField title="자기소개서" description="작성한 자기소개서가 있다면 등록해 주세요" icon={<ScrollText size={22} />} value={coverLetterFile} onChange={file(setCoverLetterFile)} />
          </div>
          <label className="consent-row">
            <input type="checkbox" checked={consented} onChange={(event) => setConsented(event.target.checked)} />
            <span><strong>면접 진행 및 데이터 처리 안내에 동의합니다.</strong><small>카메라 영상 원본은 저장하지 않으며 분석 지표만 사용합니다.</small></span>
          </label>
          <button className="button button-primary button-wide" type="button" disabled={!consented} onClick={() => onSubmit({ consented, jdFile, resumeFile, coverLetterFile })}>
            면접 준비하기
          </button>
        </section>
        <aside className="setup-aside">
          <span className="aside-kicker">Interview guide</span>
          <h2>시작 전에 확인해 주세요</h2>
          <ol className="guide-list">
            <li><span>01</span><div><strong>자료 분석</strong><p>직무와 경험을 바탕으로 질문과 평가 기준을 준비합니다.</p></div></li>
            <li><span>02</span><div><strong>환경 점검</strong><p>카메라와 마이크가 정상적으로 동작하는지 확인합니다.</p></div></li>
            <li><span>03</span><div><strong>모의 면접</strong><p>5초 준비 후 답변하며, 필요하면 꼬리질문이 이어집니다.</p></div></li>
          </ol>
        </aside>
      </div>
    </AppShell>
  );
}
