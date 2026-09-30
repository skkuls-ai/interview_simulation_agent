// Docker·Vite 모두 같은 출처의 /api를 사용하고 개발 서버가 백엔드로 프록시합니다.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

interface ApiRequestOptions {
  retryCount?: number;
}

/** 네트워크 오류와 5xx만 지정 횟수만큼 재시도합니다. */
export async function apiRequest<T>(path: string, init?: RequestInit, options: ApiRequestOptions = {}): Promise<T> {
  const retryCount = options.retryCount ?? 0;
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= retryCount; attempt += 1) {
    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}${path}`, init);
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("네트워크 요청에 실패했습니다.");
      if (attempt < retryCount) continue;
      throw lastError;
    }

    if (response.ok) return response.json() as Promise<T>;

    const body = await response.json().catch(() => null) as {
      error?: { message?: string };
      detail?: string;
    } | null;
    lastError = new Error(body?.error?.message ?? body?.detail ?? `API request failed: ${response.status}`);
    if (response.status >= 500 && attempt < retryCount) continue;
    throw lastError;
  }

  throw lastError ?? new Error("API 요청에 실패했습니다.");
}
