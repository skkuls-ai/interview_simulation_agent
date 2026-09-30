import { Check } from "lucide-react";
import { createContext, useContext } from "react";
import type { AppStep } from "../types/interview";

export const StepContext = createContext<AppStep | null>(null);

const flow: Array<{ step: AppStep; label: string }> = [
  { step: "DOCUMENT_UPLOAD", label: "파일 업로드" },
  { step: "PREPARING", label: "파일 분석" },
  { step: "DEVICE_CHECK", label: "면접 대기실" },
  { step: "INTERVIEW", label: "면접" },
  { step: "EVALUATING", label: "결과 분석" },
  { step: "REPORT", label: "결과" },
];

export function StepProgress() {
  const current = useContext(StepContext);
  const currentIndex = flow.findIndex((item) => item.step === current);
  if (currentIndex < 0 || current === "INTERVIEW") return null;

  return (
    <nav className="step-progress" aria-label="진행 단계">
      <ol>
        {flow.map((item, index) => {
          const state = index < currentIndex ? "is-done" : index === currentIndex ? "is-current" : "";
          return (
            <li className={state} key={item.step} aria-current={index === currentIndex ? "step" : undefined}>
              <span className="step-mark">{index < currentIndex ? <Check size={14} strokeWidth={3} /> : index + 1}</span>
              <span className="step-label">{item.label}</span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
