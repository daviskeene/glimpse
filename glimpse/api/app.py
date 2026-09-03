"""FastAPI application factory."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .. import __version__
from ..config import Settings, get_settings
from ..runners import Runner, create_runner
from .errors import BodyTooLargeError, error_response, register_error_handlers
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


class BodyLimitMiddleware:
    """Cap the request body as it is *read*, not just via Content-Length.

    Defense in depth behind the header checks in ``create_app``: FastAPI buffers the
    whole body before route dependencies (auth, rate limit) run, so nothing that reaches
    the app may stream more than ``max_body`` bytes — whatever the transfer encoding and
    whatever future endpoints do with the body. Exceeding the cap raises
    :class:`BodyTooLargeError`, which the registered handler maps to ``413``.
    """

    def __init__(self, app: ASGIApp, max_body: int) -> None:
        self.app = app
        self.max_body = max_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        received = 0

        async def guarded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body:
                    raise BodyTooLargeError(self.max_body)
            return message

        await self.app(scope, guarded_receive, send)


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

    # Raw JSON is larger than the fields it carries (escapes can inflate ~6x worst case);
    # this guard is a DoS backstop, the precise limits are enforced after parsing.
    max_body = 6 * (settings.max_code_bytes + settings.max_stdin_bytes) + 16384

    @app.middleware("http")
    async def request_id_and_body_guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        length = request.headers.get("content-length")
        response: Response
        if request.method == "POST" and (length is None or not length.isdigit()):
            # Chunked/unlengthed bodies would be buffered unbounded before any dependency
            # (auth, rate limit) runs; every legitimate client declares Content-Length.
            response = error_response(
                411, "length_required", "POST requests must declare a Content-Length"
            )
        elif length and length.isdigit() and int(length) > max_body:
            response = error_response(
                413, "payload_too_large", f"request body exceeds {max_body} bytes"
            )
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    app.add_middleware(BodyLimitMiddleware, max_body=max_body)
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
