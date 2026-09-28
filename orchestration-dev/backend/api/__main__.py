"""python -m backend.api 로 서버를 실행합니다."""

import uvicorn

from ..config import settings

if __name__ == "__main__":
    uvicorn.run("backend.api.main:app", host=settings.host, port=settings.port, reload=settings.debug)
