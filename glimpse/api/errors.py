"""Structured error responses: every non-2xx body is ``{"error": {"code", "message"}}``."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from ..execution import NoCapacityError, RunnerError
from ..languages import UnsupportedLanguageError

log = logging.getLogger("glimpse.api")


class APIError(Exception):
    """An error with a stable machine-readable ``code``."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers or {}


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: Any | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body, headers=headers)


_HTTP_CODES = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    415: "unsupported_media_type",
    429: "rate_limited",
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError) -> JSONResponse:
        return error_response(
            exc.status_code, exc.code, exc.message, details=exc.details, headers=exc.headers
        )

    @app.exception_handler(UnsupportedLanguageError)
    async def _unsupported(_: Request, exc: UnsupportedLanguageError) -> JSONResponse:
        return error_response(400, "unsupported_language", str(exc))

    @app.exception_handler(NoCapacityError)
    async def _no_capacity(_: Request, exc: NoCapacityError) -> JSONResponse:
        return error_response(
            503, "no_capacity", f"{exc}; retry shortly", headers={"Retry-After": "1"}
        )

    @app.exception_handler(RunnerError)
    async def _runner_error(_: Request, exc: RunnerError) -> JSONResponse:
        log.error("runner error: %s", exc)
        return error_response(500, "runner_error", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "loc": [str(part) for part in err.get("loc", ())],
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]
        return error_response(422, "validation_error", "request validation failed", details=errors)

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return error_response(
            exc.status_code, code, message, headers=dict(exc.headers) if exc.headers else None
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return error_response(500, "internal_error", "internal server error")
