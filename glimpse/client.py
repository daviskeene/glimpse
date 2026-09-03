"""Python client for a Glimpse server.

    from glimpse.client import GlimpseClient

    with GlimpseClient("http://localhost:8000") as client:
        result = client.execute("python", "print(input())", stdin="hi")
        print(result.stdout)          # "hi\\n"

``AsyncGlimpseClient`` offers the same methods as coroutines.
"""

from __future__ import annotations

import os
from types import TracebackType
from typing import Any

import httpx

from . import __version__
from .models import ExecuteResponse, HealthResponse, LanguageInfo

DEFAULT_URL = "http://localhost:8000"
USER_AGENT = f"glimpse-client/{__version__}"


class GlimpseError(Exception):
    """Base class for client errors."""


class GlimpseAPIError(GlimpseError):
    """The server answered with an error (``{"error": {"code", "message"}}``)."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: Any | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(f"{status_code} {code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.retry_after = retry_after


class GlimpseConnectionError(GlimpseError):
    """The server could not be reached."""


def _headers(api_key: str | None) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _raise_for_error(response: httpx.Response) -> None:
    if response.is_success:
        return
    code, message, details = "http_error", response.reason_phrase or "request failed", None
    try:
        payload = response.json()
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict):
            code = str(err.get("code", code))
            message = str(err.get("message", message))
            details = err.get("details")
    except ValueError:
        pass
    retry_after: float | None = None
    header = response.headers.get("retry-after")
    if header and header.replace(".", "", 1).isdigit():
        retry_after = float(header)
    raise GlimpseAPIError(
        response.status_code, code, message, details=details, retry_after=retry_after
    )


def _execute_body(language: str, code: str, stdin: str, timeout_s: float | None) -> dict[str, Any]:
    body: dict[str, Any] = {"language": language, "code": code, "stdin": stdin}
    if timeout_s is not None:
        body["timeout_s"] = timeout_s
    return body


def _resolve_url(base_url: str | None) -> str:
    return (base_url or os.environ.get("GLIMPSE_URL") or DEFAULT_URL).rstrip("/")


class GlimpseClient:
    """Synchronous client."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        api_key: str | None = None,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = _resolve_url(base_url)
        api_key = api_key or os.environ.get("GLIMPSE_API_KEY")
        self._http = httpx.Client(
            base_url=self.base_url,
            headers=_headers(api_key),
            timeout=timeout,
            transport=transport,
        )

    def execute(
        self, language: str, code: str, *, stdin: str = "", timeout_s: float | None = None
    ) -> ExecuteResponse:
        response = self._request(
            "POST", "/v1/execute", json=_execute_body(language, code, stdin, timeout_s)
        )
        return ExecuteResponse.model_validate(response.json())

    def languages(self) -> list[LanguageInfo]:
        response = self._request("GET", "/v1/languages")
        return [LanguageInfo.model_validate(item) for item in response.json()]

    def health(self) -> HealthResponse:
        response = self._request("GET", "/health")
        return HealthResponse.model_validate(response.json())

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise GlimpseConnectionError(f"could not reach {self.base_url}: {exc}") from exc
        _raise_for_error(response)
        return response

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> GlimpseClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


class AsyncGlimpseClient:
    """Asynchronous client with the same surface as :class:`GlimpseClient`."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        api_key: str | None = None,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = _resolve_url(base_url)
        api_key = api_key or os.environ.get("GLIMPSE_API_KEY")
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers=_headers(api_key),
            timeout=timeout,
            transport=transport,
        )

    async def execute(
        self, language: str, code: str, *, stdin: str = "", timeout_s: float | None = None
    ) -> ExecuteResponse:
        response = await self._request(
            "POST", "/v1/execute", json=_execute_body(language, code, stdin, timeout_s)
        )
        return ExecuteResponse.model_validate(response.json())

    async def languages(self) -> list[LanguageInfo]:
        response = await self._request("GET", "/v1/languages")
        return [LanguageInfo.model_validate(item) for item in response.json()]

    async def health(self) -> HealthResponse:
        response = await self._request("GET", "/health")
        return HealthResponse.model_validate(response.json())

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise GlimpseConnectionError(f"could not reach {self.base_url}: {exc}") from exc
        _raise_for_error(response)
        return response

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncGlimpseClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
