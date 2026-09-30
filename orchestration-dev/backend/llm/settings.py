"""LLM 설정. 역할별 모델과 추론 수준을 한곳에서 관리합니다. 값은 .env 에서 읽습니다.

연결 방식 (위에서부터 우선)
    1. Vertex AI + gcloud 로그인 (권장, 학교 프로젝트)
         GOOGLE_CLOUD_PROJECT=<프로젝트 ID>, GOOGLE_CLOUD_LOCATION=global
         인증: gcloud auth application-default login
    2. Vertex AI + API 키 (express mode)
         GOOGLE_GENAI_USE_VERTEXAI=true, GEMINI_API_KEY=<Vertex 에서 만든 키>
    3. Gemini API (Google AI Studio 키)
         GEMINI_API_KEY=<AI Studio 키>

모델
    GEMINI_MODEL              기본 모델 (검증 역할 제외 전체). 기본 gemini-3.8-flash
    INTERVIEW_MODEL_<ROLE>    역할별 덮어쓰기. 예: INTERVIEW_MODEL_VALIDATOR=gemini-3.7-flash
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field

ThinkingLevel = Literal["LOW", "MEDIUM", "HIGH"]  # 3.8 Flash 는 MINIMAL 미지원


class RoleSettings(BaseModel):
    model: str
    thinking_level: ThinkingLevel
    timeout_sec: float = Field(description="한 번 호출의 최대 대기 시간")
    retries: int = Field(1, description="실패 시 재시도 횟수")


DEFAULT_ROLES: dict[str, RoleSettings] = {
    # 지원자가 기다리는 구간: 속도 우선
    "follow_up_judge": RoleSettings(model="gemini-3.8-flash", thinking_level="LOW", timeout_sec=8, retries=1),
    "intro_check": RoleSettings(model="gemini-3.8-flash", thinking_level="LOW", timeout_sec=10, retries=1),
    # 백그라운드, 면접 전후: 품질 우선
    "evaluator": RoleSettings(model="gemini-3.8-flash", thinking_level="MEDIUM", timeout_sec=60, retries=2),
    "analysis": RoleSettings(model="gemini-3.8-flash", thinking_level="MEDIUM", timeout_sec=90, retries=2),
    "feedback": RoleSettings(model="gemini-3.8-flash", thinking_level="HIGH", timeout_sec=120, retries=2),
    # 만든 모델과 다른 모델로 검사
    "validator": RoleSettings(model="gemini-3.7-flash", thinking_level="MEDIUM", timeout_sec=60, retries=2),
}


class LLMSettings(BaseModel):
    project: str | None = None
    location: str = "global"
    api_key: str | None = None
    use_vertex: bool = True
    roles: dict[str, RoleSettings] = Field(default_factory=lambda: {k: v.model_copy() for k, v in DEFAULT_ROLES.items()})

    @classmethod
    def from_env(cls) -> "LLMSettings":
        from .. import config  # noqa: F401  (.env 로드)

        project = os.environ.get("GOOGLE_CLOUD_PROJECT") or None
        vertex_flag = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in ("1", "true", "yes")
        s = cls(
            project=project,
            location=os.environ.get("GOOGLE_CLOUD_LOCATION") or "global",
            api_key=os.environ.get("GEMINI_API_KEY") or None,
            use_vertex=bool(project) or vertex_flag,
        )
        if base := os.environ.get("GEMINI_MODEL"):
            for role, cfg in s.roles.items():
                if cfg.model == DEFAULT_ROLES[role].model and role != "validator":
                    s.roles[role] = cfg.model_copy(update={"model": base})
        for role, cfg in s.roles.items():
            if m := os.environ.get(f"INTERVIEW_MODEL_{role.upper()}"):
                s.roles[role] = cfg.model_copy(update={"model": m})
        return s

    def role(self, name: str) -> RoleSettings:
        return self.roles[name]
