"""오류 응답 형식: {"error": {"code": "...", "message": "..."}} (04 문서 4장)."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .schemas.api import ERROR_CODES, ErrorBody, ErrorResponse


class ApiError(Exception):
    def __init__(self, code: str, message: str, field: str | None = None):
        if code not in ERROR_CODES:
            raise ValueError(f"알 수 없는 오류 코드: {code}")
        self.code, self.message, self.field = code, message, field


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        body = ErrorResponse(error=ErrorBody(code=exc.code, message=exc.message, field=exc.field))
        return JSONResponse(status_code=ERROR_CODES[exc.code], content=body.model_dump(exclude_none=True))
