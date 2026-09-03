from __future__ import annotations

import json

import httpx
import pytest

from glimpse.api import create_app
from glimpse.client import (
    AsyncGlimpseClient,
    GlimpseAPIError,
    GlimpseClient,
    GlimpseConnectionError,
)
from tests.conftest import FakeRunner, make_settings


def _mock_transport(fake_runner: FakeRunner) -> httpx.MockTransport:
    """Route the sync client through the ASGI app without a network."""
    app = create_app(make_settings(), runner=fake_runner)

    def handler(request: httpx.Request) -> httpx.Response:
        from fastapi.testclient import TestClient

        with TestClient(app) as tc:
            resp = tc.request(
                request.method,
                request.url.path,
                content=request.content,
                headers=dict(request.headers),
            )
        return httpx.Response(resp.status_code, content=resp.content, headers=resp.headers)

    return httpx.MockTransport(handler)


def test_sync_client_execute(fake_runner: FakeRunner) -> None:
    with GlimpseClient(
        "http://glimpse.test", api_key="k", transport=_mock_transport(fake_runner)
    ) as client:
        result = client.execute("py", "print(1)", stdin="in", timeout_s=4)
        assert result.language == "python"
        assert result.stdout == "hello\n"
        assert fake_runner.calls[0]["timeout_s"] == 4.0
        langs = client.languages()
        assert langs[0].id == "python"
        assert client.health().status == "ok"


def test_sync_client_raises_api_error(fake_runner: FakeRunner) -> None:
    with GlimpseClient("http://glimpse.test", transport=_mock_transport(fake_runner)) as client:
        with pytest.raises(GlimpseAPIError) as exc:
            client.execute("cobol", "x")
        assert exc.value.status_code == 400
        assert exc.value.code == "unsupported_language"
        assert "cobol" in str(exc.value)


def test_sync_client_retry_after() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"error": {"code": "no_capacity", "message": "busy"}},
            headers={"Retry-After": "3"},
        )

    with GlimpseClient("http://x", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GlimpseAPIError) as exc:
            client.execute("python", "x")
        assert exc.value.retry_after == 3.0
        assert exc.value.code == "no_capacity"


def test_sync_client_non_json_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    with GlimpseClient("http://x", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GlimpseAPIError) as exc:
            client.languages()
        assert exc.value.status_code == 502
        assert exc.value.code == "http_error"


def test_sync_client_connection_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with (
        GlimpseClient("http://x", transport=httpx.MockTransport(handler)) as client,
        pytest.raises(GlimpseConnectionError),
    ):
        client.health()


def test_client_sends_api_key_and_body() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "language": "python",
                "phase": "run",
                "exit_code": 0,
                "timed_out": False,
                "stdout": "",
                "stderr": "",
                "duration_ms": 1,
            },
        )

    with GlimpseClient("http://x/", api_key="sekrit", transport=httpx.MockTransport(handler)) as c:
        assert c.base_url == "http://x"
        c.execute("python", "x")
    assert seen["auth"] == "Bearer sekrit"
    assert seen["body"] == {"language": "python", "code": "x", "stdin": ""}


def test_client_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GLIMPSE_URL", "http://env.test/")
    monkeypatch.setenv("GLIMPSE_API_KEY", "envkey")
    client = GlimpseClient()
    assert client.base_url == "http://env.test"
    assert client._http.headers["authorization"] == "Bearer envkey"
    client.close()


async def test_async_client(fake_runner: FakeRunner) -> None:
    app = create_app(make_settings(), runner=fake_runner)
    transport = httpx.ASGITransport(app=app)
    async with AsyncGlimpseClient("http://glimpse.test", transport=transport) as client:
        result = await client.execute("python", "print(1)")
        assert result.stdout == "hello\n"
        assert (await client.health()).runner == "fake"
        assert (await client.languages())[0].id == "python"
        with pytest.raises(GlimpseAPIError) as exc:
            await client.execute("cobol", "x")
        assert exc.value.code == "unsupported_language"
