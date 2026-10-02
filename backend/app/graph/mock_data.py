"""shared/mock JSON 로더. 가짜 진행기와, 질문 생성(B)이 합류하기 전 임시 질문 채우기에 쓴다."""
import json
import os
from pathlib import Path


def mock_dir() -> Path:
    if os.environ.get("MOCK_DIR"):
        return Path(os.environ["MOCK_DIR"])
    here = Path(__file__).resolve()
    # 저장소: backend/app/graph/ → parents[3]가 루트, Docker: /srv/app/graph/ → parents[2]가 /srv
    for base in (here.parents[3], here.parents[2]):
        if (base / "shared" / "mock").is_dir():
            return base / "shared" / "mock"
    raise FileNotFoundError("shared/mock 폴더를 찾을 수 없다 (MOCK_DIR로 지정 가능)")


def load(name: str) -> dict:
    return json.loads((mock_dir() / name).read_text(encoding="utf-8"))
