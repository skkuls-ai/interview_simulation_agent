import { ScanFace, ShieldCheck } from "lucide-react";
import type { PropsWithChildren } from "react";

interface AppShellProps extends PropsWithChildren {
  title?: string;
  description?: string;
}

export function AppShell({ title, description, children }: AppShellProps) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-inner">
          <a className="brand" href="/" aria-label="Interview Simulation 홈">
            <span className="brand-mark"><ScanFace size={18} strokeWidth={2.2} /></span>
            <span>Interview Simulation</span>
          </a>
          <div className="privacy-note">
            <ShieldCheck size={16} />
            <span>영상 원본은 저장하지 않습니다</span>
          </div>
        </div>
      </header>
      <main className="app-main">
        {(title || description) && (
          <div className="page-heading">
            {title && <h1>{title}</h1>}
            {description && <p className="description">{description}</p>}
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
