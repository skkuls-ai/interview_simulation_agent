"""Gemini 호출을 감싸는 얇은 클라이언트. 출처: feature/orchestration 의 backend/llm/client.py (9/28, 실측 42/42).

에이전트는 이 인터페이스(JsonLLM)에만 의존하므로 테스트에서는 가짜 구현으로 바꿔 끼웁니다.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from .settings import LLMSettings, RoleSettings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


RATE_LIMIT_WAIT_SEC = 2.0


def is_rate_limited(e: Exception) -> bool:
    text = str(e)
    return "429" in text or "RESOURCE_EXHAUSTED" in text


class LLMError(Exception):
    """호출 실패, 시간 초과, 스키마에 맞지 않는 응답."""


@dataclass
class CallInfo:
    role: str
    model: str
    latency_sec: float
    attempts: int
    input_tokens: int | None = None
    output_tokens: int | None = None


class JsonLLM(Protocol):
    def generate_json(self, role: str, system: str, prompt: str, schema: type[T]) -> tuple[T, CallInfo]: ...


def inline_refs(schema: dict) -> dict:
    """$ref 와 $defs 를 펼칩니다. 구조화 출력 스키마 지원 범위가 모델마다 달라 가장 단순한 형태로 보냄."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


class GeminiClient:
    """Vertex AI 의 Gemini 를 구조화 출력(JSON 스키마)으로 호출합니다."""

    def __init__(self, settings: LLMSettings | None = None, client=None):
        self.settings = settings or LLMSettings.from_env()
        self.client = client or self._make_client(self.settings)

    @staticmethod
    def _make_client(s: LLMSettings):
        from google import genai

        if s.use_vertex and s.project:
            return genai.Client(vertexai=True, project=s.project, location=s.location)
        if s.use_vertex and s.api_key:
            return genai.Client(vertexai=True, api_key=s.api_key)
        if s.api_key:
            return genai.Client(api_key=s.api_key)
        raise LLMError(
            "Gemini 연결 정보가 없습니다. .env 에 GOOGLE_CLOUD_PROJECT (Vertex AI, 권장) 또는 GEMINI_API_KEY 를 넣어 주세요."
        )

    def _config(self, cfg: RoleSettings, system: str, schema: type[BaseModel]):
        from google.genai import types

        # 3.8 Flash 는 temperature, top_p, top_k 를 받지 않고 thinking_level 로 조절
        return types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=inline_refs(schema.model_json_schema()),
            thinking_config=types.ThinkingConfig(thinking_level=cfg.thinking_level),
            http_options=types.HttpOptions(timeout=int(cfg.timeout_sec * 1000)),
        )

    def generate_json(self, role: str, system: str, prompt: str, schema: type[T]) -> tuple[T, CallInfo]:
        cfg = self.settings.role(role)
        last: Exception | None = None
        t0 = time.perf_counter()
        for attempt in range(1, cfg.retries + 2):
            try:
                resp = self.client.models.generate_content(
                    model=cfg.model, contents=prompt, config=self._config(cfg, system, schema)
                )
                text = resp.text or ""
                obj = schema.model_validate_json(text)
                usage = getattr(resp, "usage_metadata", None)
                info = CallInfo(
                    role=role, model=cfg.model, latency_sec=round(time.perf_counter() - t0, 3), attempts=attempt,
                    input_tokens=getattr(usage, "prompt_token_count", None),
                    output_tokens=getattr(usage, "candidates_token_count", None),
                )
                log.info("LLM %s %s %.2fs (시도 %d)", role, cfg.model, info.latency_sec, attempt)
                return obj, info
            except ValidationError as e:
                last = e
                log.warning("LLM %s 응답이 스키마와 다름 (시도 %d): %s", role, attempt, e.errors()[:2])
            except Exception as e:  # 네트워크, 시간 초과, 할당량 초과 등
                last = e
                log.warning("LLM %s 호출 실패 (시도 %d): %s", role, attempt, e)
                if is_rate_limited(e) and attempt <= cfg.retries:
                    time.sleep(RATE_LIMIT_WAIT_SEC)  # 429 는 바로 다시 부르면 또 막히기 쉬움
            # 이미 오래 기다렸으면 재시도하지 않음 (지원자 대기 시간이 두 배가 되지 않도록)
            if time.perf_counter() - t0 > cfg.timeout_sec / 2:
                break
        raise LLMError(f"{role} 호출 실패: {last}") from last
