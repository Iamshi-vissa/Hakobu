"""API error envelope: ``{"error": {"code": ..., "message": ...}}``."""

from __future__ import annotations

from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ErrorCode(StrEnum):
    UNSUPPORTED_FORMAT = "unsupported_format"
    UNSUPPORTED_CONVERSION = "unsupported_conversion"
    TOO_LARGE = "too_large"
    CORRUPTED = "corrupted"
    FAILED = "failed"
    NOT_FOUND = "not_found"
    NOT_READY = "not_ready"
    UPLOAD_CONFLICT = "upload_conflict"
    RATE_LIMITED = "rate_limited"
    INVALID_REQUEST = "invalid_request"


class ApiError(Exception):
    def __init__(self, status: int, code: ErrorCode, message: str, **extra: object) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def _body(code: str, message: str, **extra: object) -> dict[str, object]:
    return {"error": {"code": code, "message": message, **extra}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, **exc.extra), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        message = f"{where}: {first.get('msg', 'invalid value')}" if where else "Invalid request."
        return JSONResponse(_body(ErrorCode.INVALID_REQUEST, message), status_code=422)
