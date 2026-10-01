import { useEffect, useState } from "react";
import { ApiError } from "./client";
import { getInterview, type InterviewStatusResponse } from "./interview";

const POLL_INTERVAL_MS = 2000;

/** 2초마다 세션 상태를 읽고, done(status)가 참이 되거나 FAILED가 되면 멈춥니다. 세션이 없으면(404) FAILED로 보고 멈추고, 일시적인 네트워크 오류는 다음 주기에 다시 시도합니다. */
export function useSessionStatus(sessionId: string | null, done: (status: InterviewStatusResponse["status"]) => boolean) {
  const [data, setData] = useState<InterviewStatusResponse | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    let stopped = false;
    let timer: number | undefined;
    const tick = async () => {
      let finished = false;
      try {
        const next = await getInterview(sessionId);
        if (stopped) return;
        setData(next);
        finished = next.status === "FAILED" || done(next.status);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          // 서버 재시작 등으로 세션이 사라짐: 화면이 FAILED 안내와 「처음으로」를 보이도록 한다
          if (!stopped) setData({ session_id: sessionId, status: "FAILED", steps: [], questions: null, error: "서버에서 면접 정보를 찾을 수 없습니다. 처음부터 다시 시작해 주세요." });
          return;
        }
        // 일시적인 네트워크 오류는 다음 주기에 다시 시도
      }
      if (!stopped && !finished) timer = window.setTimeout(tick, POLL_INTERVAL_MS);
    };
    void tick();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  return data;
}
