"""The ``/v1`` routes."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Request

from .. import __version__, languages
from ..config import Settings
from ..execution import RunnerError
from ..models import (
    ErrorResponse,
    ExecuteRequest,
    ExecuteResponse,
    HealthResponse,
    LanguageInfo,
)
from ..runners import Runner
from .errors import APIError, error_response
from .security import enforce_rate_limit, require_api_key

log = logging.getLogger("glimpse.api")

router = APIRouter()

_ERR = {"model": ErrorResponse}
EXECUTE_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {**_ERR, "description": "Unsupported language"},
    401: {**_ERR, "description": "Missing or invalid API key (only when keys are configured)"},
    413: {**_ERR, "description": "`code` or `stdin` exceeds the configured size limit"},
    422: {**_ERR, "description": "Request validation failed"},
    429: {**_ERR, "description": "Rate limit exceeded; see `Retry-After`"},
    500: {**_ERR, "description": "The execution backend failed"},
    503: {**_ERR, "description": "No sandbox capacity right now; see `Retry-After`"},
}


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _runner(request: Request) -> Runner:
    runner: Runner = request.app.state.runner
    return runner


@router.get("/", include_in_schema=False)
async def index(request: Request) -> dict[str, Any]:
    return {
        "name": "glimpse",
        "version": __version__,
        "runner": _runner(request).name,
        "docs": "/docs",
        "endpoints": {
            "execute": "POST /v1/execute",
            "languages": "GET /v1/languages",
            "health": "GET /health",
        },
    }


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {**_ERR, "description": "Backend unhealthy"}},
    tags=["meta"],
)
async def health(request: Request) -> Any:
    runner = _runner(request)
    try:
        details = await runner.health()
    except RunnerError as exc:
        return error_response(503, "unhealthy", str(exc))
    return HealthResponse(status="ok", runner=runner.name, version=__version__, details=details)


@router.get("/v1/languages", response_model=list[LanguageInfo], tags=["v1"])
async def list_languages(request: Request) -> list[LanguageInfo]:
    """Supported languages, their accepted aliases and (when known) toolchain versions."""
    runner = _runner(request)
    try:
        versions = await runner.versions()
    except RunnerError as exc:
        log.warning("could not probe toolchain versions: %s", exc)
        versions = {}
    return [
        LanguageInfo(
            id=lang.id,
            name=lang.name,
            aliases=list(lang.aliases),
            version=versions.get(lang.id),
            compiled=lang.compiled,
            filename=lang.filename,
            sample=lang.sample,
        )
        for lang in languages.LANGUAGES
    ]


@router.post(
    "/v1/execute",
    response_model=ExecuteResponse,
    responses=EXECUTE_RESPONSES,
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
    tags=["v1"],
    summary="Run a code snippet",
)
async def execute(body: ExecuteRequest, request: Request) -> ExecuteResponse:
    """Compile (if needed) and run a snippet in an isolated sandbox.

    Failures of the *program* (compile errors, non-zero exits, timeouts) are returned
    as `200` results — inspect `phase`, `exit_code` and `timed_out`. Only failures of
    the *service* produce error status codes.
    """
    settings = _settings(request)
    runner = _runner(request)
    language = languages.resolve(body.language)

    code_bytes = len(body.code.encode("utf-8"))
    if code_bytes > settings.max_code_bytes:
        raise APIError(
            413,
            "code_too_large",
            f"code is {code_bytes} bytes; the limit is {settings.max_code_bytes} bytes",
        )
    stdin_bytes = len(body.stdin.encode("utf-8"))
    if stdin_bytes > settings.max_stdin_bytes:
        raise APIError(
            413,
            "stdin_too_large",
            f"stdin is {stdin_bytes} bytes; the limit is {settings.max_stdin_bytes} bytes",
        )
    timeout_s = settings.clamp_timeout(body.timeout_s)

    started = time.monotonic()
    result = await runner.execute(language, body.code, stdin=body.stdin, timeout_s=timeout_s)
    log.info(
        "execute language=%s phase=%s exit=%d timed_out=%s duration_ms=%d total_ms=%d runner=%s",
        result.language,
        result.phase,
        result.exit_code,
        result.timed_out,
        result.duration_ms,
        int((time.monotonic() - started) * 1000),
        runner.name,
    )
    return ExecuteResponse(**result.to_dict())
