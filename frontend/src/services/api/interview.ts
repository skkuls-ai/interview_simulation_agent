import type { InterviewPrompt, SessionSetup } from "../../types/interview";
import { apiRequest } from "./client";

export async function createSession(setup: SessionSetup) {
  const formData = new FormData();
  formData.append("consented", String(setup.consented));

  if (setup.jdFile) formData.append("jd", setup.jdFile);
  if (setup.resumeFile) formData.append("resume", setup.resumeFile);
  if (setup.coverLetterFile) formData.append("cover_letter", setup.coverLetterFile);

  return apiRequest<{ sessionId: string }>("/api/sessions", {
    method: "POST",
    body: formData,
  });
}

export function getNextPrompt(sessionId: string) {
  return apiRequest<InterviewPrompt>(`/api/sessions/${sessionId}/next-prompt`);
}
