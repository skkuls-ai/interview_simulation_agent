"""앱 설정. 프로젝트 루트의 .env 를 읽습니다 (이미 설정된 환경변수가 우선)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class AppSettings(BaseModel):
    app_name: str = "Interview Simulator"
    app_version: str = "1.0.0"
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    frontend_origin: str = "http://localhost:5173"
    data_dir: Path = ROOT / "var"
    use_llm: bool = False
    bg_llm_concurrency: int = 3  # 백그라운드 평가의 LLM 동시 호출 수 (학교 할당량에 맞춰 조절)

    @classmethod
    def load(cls) -> "AppSettings":
        return cls(
            app_name=os.environ.get("APP_NAME") or cls.model_fields["app_name"].default,
            app_version=os.environ.get("APP_VERSION", "1.0.0"),
            host=os.environ.get("APP_HOST", "127.0.0.1"),
            port=int(os.environ.get("APP_PORT", "8000")),
            debug=_bool("DEBUG"),
            frontend_origin=os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173"),
            data_dir=Path(os.environ.get("INTERVIEW_DATA_DIR") or ROOT / "var"),
            use_llm=_bool("INTERVIEW_USE_LLM"),
            bg_llm_concurrency=int(os.environ.get("INTERVIEW_BG_LLM_CONCURRENCY", "3")),
        )


settings = AppSettings.load()
