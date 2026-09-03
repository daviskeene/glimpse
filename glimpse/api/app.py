"""FastAPI application factory."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..config import Settings, get_settings
from ..runners import Runner, create_runner
from .errors import error_response, register_error_handlers
from .routes import router
from .security import SlidingWindowLimiter, parse_rate_limit

log = logging.getLogger("glimpse.api")

DESCRIPTION = """
Run untrusted code snippets in isolated sandboxes.

* `POST /v1/execute` — compile (if needed) and run a snippet; program failures are
  returned as normal `200` results with `phase`, `exit_code` and `timed_out`.
* `GET /v1/languages` — supported languages, aliases and toolchain versions.
* `GET /health` — backend status.

Every error response has the shape `{"error": {"code": "...", "message": "..."}}`.
"""


def create_app(settings: Settings | None = None, runner: Runner | None = None) -> FastAPI:
    settings = settings or get_settings()
    runner = runner or create_runner(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await runner.start()
        try:
            yield
        finally:
            await runner.stop()

    app = FastAPI(
        title="Glimpse",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.state.settings = settings
    app.state.runner = runner
    app.state.rate_limiter = (
        SlidingWindowLimiter(*parse_rate_limit(settings.rate_limit))
        if settings.rate_limit
        else None
    )
    app.state.global_limiter = (
        SlidingWindowLimiter(*parse_rate_limit(settings.global_rate_limit))
        if settings.global_rate_limit
        else None
    )

    max_body = settings.max_code_bytes + settings.max_stdin_bytes + 4096

    @app.middleware("http")
    async def request_id_and_body_guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        length = request.headers.get("content-length")
        response: Response
        if length and length.isdigit() and int(length) > max_body:
            response = error_response(
                413, "payload_too_large", f"request body exceeds {max_body} bytes"
            )
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    register_error_handlers(app)
    app.include_router(router)
    return app


def app() -> FastAPI:
    """Uvicorn factory entry point: ``uvicorn glimpse.api.app:app --factory``."""
    return create_app()
