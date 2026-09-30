"""그래프가 쓸 LLM과 실행 모드를 정한다.

INTERVIEW_GRAPH_MODE: auto(기본) | real | fake
- auto: GOOGLE_CLOUD_PROJECT 또는 GEMINI_API_KEY가 있으면 real, 없으면 fake
- fake: shared/mock을 재생하는 가짜 진행기(graph/fake.py). LLM 호출 없음
- real: 진짜 그래프. 자격 정보가 없으면 준비 그래프가 FAILED로 끝난다
"""
import logging
import os
import threading

from ..llm.settings import LLMSettings

log = logging.getLogger(__name__)
_lock = threading.Lock()
_client = None


def graph_mode() -> str:
    mode = os.environ.get("INTERVIEW_GRAPH_MODE", "auto").strip().lower()
    if mode in ("fake", "real"):
        return mode
    settings = LLMSettings.from_env()  # 저장소 루트 .env도 읽는다
    return "real" if (settings.project or settings.api_key) else "fake"


def get_llm():
    """준비·평가가 함께 쓰는 GeminiClient (프로세스당 하나)."""
    global _client
    with _lock:
        if _client is None:
            from ..llm.client import GeminiClient

            _client = GeminiClient(LLMSettings.from_env())
            log.info("LLM 클라이언트 생성")
        return _client
