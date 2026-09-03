from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glimpse import __version__
from glimpse.api import create_app
from glimpse.execution import NoCapacityError, RunnerError
from tests.conftest import FakeRunner, make_settings


def test_index_lists_endpoints(client: TestClient) -> None:
    body = client.get("/").json()
    assert body["name"] == "glimpse"
    assert body["version"] == __version__
    assert body["endpoints"]["execute"] == "POST /v1/execute"


def test_health_ok(client: TestClient, fake_runner: FakeRunner) -> None:
    assert fake_runner.started
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["runner"] == "fake"
    assert body["details"] == {"fake": True}


def test_health_unhealthy(client: TestClient, fake_runner: FakeRunner) -> None:
    fake_runner.fail_with = RunnerError("daemon gone")
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "unhealthy", "message": "daemon gone"}}


def test_languages(client: TestClient) -> None:
    response = client.get("/v1/languages")
    assert response.status_code == 200
    items = response.json()
    ids = [item["id"] for item in items]
    assert ids == [
        "python",
        "javascript",
        "typescript",
        "bash",
        "c",
        "cpp",
        "rust",
        "go",
        "java",
        "kotlin",
    ]
    python = items[0]
    assert python["aliases"] == ["py", "python3", "py3"]
    assert python["version"] == "Python 3.99"
    assert python["compiled"] is False
    assert python["filename"] == "main.py"
    assert "hello" in python["sample"]
    c = next(item for item in items if item["id"] == "c")
    assert c["compiled"] is True
    assert c["version"] is None


def test_execute_happy_path(client: TestClient, fake_runner: FakeRunner) -> None:
    response = client.post(
        "/v1/execute", json={"language": "py", "code": "print(1)", "stdin": "x", "timeout_s": 5}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "language": "python",
        "phase": "run",
        "exit_code": 0,
        "timed_out": False,
        "stdout": "hello\n",
        "stderr": "",
        "duration_ms": 7,
        "truncated": False,
        "compile_stderr": "",
    }
    assert fake_runner.calls == [
        {"language": "python", "code": "print(1)", "stdin": "x", "timeout_s": 5.0}
    ]
    assert response.headers["x-request-id"]


def test_execute_uses_default_timeout_and_clamps(fake_runner: FakeRunner) -> None:
    settings = make_settings(default_timeout_s=3, max_timeout_s=8)
    with TestClient(create_app(settings, runner=fake_runner)) as client:
        client.post("/v1/execute", json={"language": "python", "code": "x"})
        client.post("/v1/execute", json={"language": "python", "code": "x", "timeout_s": 30})
    assert [call["timeout_s"] for call in fake_runner.calls] == [3.0, 8.0]


def test_program_failures_are_200(client: TestClient, fake_runner: FakeRunner) -> None:
    fake_runner.result.phase = "compile"
    fake_runner.result.exit_code = 1
    fake_runner.result.stderr = "error: expected ';'"
    response = client.post("/v1/execute", json={"language": "c", "code": "int main("})
    assert response.status_code == 200
    assert response.json()["phase"] == "compile"
    assert response.json()["exit_code"] == 1


@pytest.mark.parametrize(
    ("alias", "canonical"), [("sh", "bash"), ("ts", "typescript"), ("rs", "rust")]
)
def test_fence_aliases_resolve(
    client: TestClient, fake_runner: FakeRunner, alias: str, canonical: str
) -> None:
    response = client.post("/v1/execute", json={"language": alias, "code": "x"})
    assert response.status_code == 200
    assert response.json()["language"] == canonical
    assert fake_runner.calls[-1]["language"] == canonical


def test_unsupported_language(client: TestClient) -> None:
    response = client.post("/v1/execute", json={"language": "cobol", "code": "x"})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "unsupported_language"
    assert "cobol" in error["message"]
    assert "python" in error["message"]


def test_validation_errors_are_structured(client: TestClient) -> None:
    response = client.post("/v1/execute", json={"language": "python", "code": ""})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["body", "code"]

    response = client.post("/v1/execute", json={"language": "python", "code": "x", "nope": 1})
    assert response.status_code == 422

    response = client.post(
        "/v1/execute", json={"language": "python", "code": "x", "timeout_s": 0.5}
    )
    assert response.status_code == 422

    response = client.post(
        "/v1/execute", content=b"not json", headers={"content-type": "application/json"}
    )
    assert response.status_code == 422


def test_code_too_large(fake_runner: FakeRunner) -> None:
    settings = make_settings(max_code_bytes=10, max_stdin_bytes=5)
    with TestClient(create_app(settings, runner=fake_runner)) as client:
        response = client.post("/v1/execute", json={"language": "python", "code": "x" * 11})
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "code_too_large"
        response = client.post(
            "/v1/execute", json={"language": "python", "code": "x", "stdin": "y" * 6}
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "stdin_too_large"
        response = client.post(
            "/v1/execute",
            content=b"{" + b" " * 100_000 + b"}",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "payload_too_large"
    assert fake_runner.calls == []


def test_chunked_post_is_rejected(client: TestClient) -> None:
    """A body without Content-Length would be buffered unbounded before auth/rate limits."""

    def gen() -> object:
        yield b'{"language": "python", "code": "x"}'

    response = client.post(
        "/v1/execute", content=gen(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 411
    assert response.json()["error"]["code"] == "length_required"


async def test_body_limit_middleware_caps_streamed_bodies() -> None:
    """Defense in depth: even a body that slips past the header checks is capped as read."""
    from glimpse.api.app import BodyLimitMiddleware
    from glimpse.api.errors import BodyTooLargeError

    async def inner_app(scope: object, receive: object, send: object) -> None:
        while True:
            message = await receive()  # type: ignore[operator]
            if not message.get("more_body"):
                break

    messages = [
        {"type": "http.request", "body": b"x" * 8, "more_body": True},
        {"type": "http.request", "body": b"x" * 8, "more_body": False},
    ]

    async def receive() -> dict[str, object]:
        return messages.pop(0)

    async def send(message: object) -> None:
        pass

    middleware = BodyLimitMiddleware(inner_app, max_body=10)
    with pytest.raises(BodyTooLargeError):
        await middleware({"type": "http"}, receive, send)


def test_timeout_above_schema_floor_is_clamped_not_rejected(fake_runner: FakeRunner) -> None:
    settings = make_settings(default_timeout_s=3, max_timeout_s=8)
    with TestClient(create_app(settings, runner=fake_runner)) as client:
        response = client.post(
            "/v1/execute", json={"language": "python", "code": "x", "timeout_s": 3600}
        )
        assert response.status_code == 200
    assert fake_runner.calls[-1]["timeout_s"] == 8.0


def test_non_ascii_bearer_token_is_401_not_500(fake_runner: FakeRunner) -> None:
    settings = make_settings(api_keys="k1")
    with TestClient(create_app(settings, runner=fake_runner)) as client:
        # httpx refuses non-ASCII str header values, but raw bytes reach the ASGI app
        # exactly as a hostile client would send them (Starlette decodes headers latin-1).
        response = client.post(
            "/v1/execute",
            json={"language": "python", "code": "x"},
            headers=[(b"authorization", "Bearer caf\u00e9".encode("latin-1"))],
        )
        assert response.status_code == 401


def test_no_capacity_is_503_with_retry_after(client: TestClient, fake_runner: FakeRunner) -> None:
    fake_runner.fail_with = NoCapacityError("at capacity (4 concurrent executions)")
    response = client.post("/v1/execute", json={"language": "python", "code": "x"})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert response.json()["error"]["code"] == "no_capacity"


def test_runner_error_is_500(client: TestClient, fake_runner: FakeRunner) -> None:
    fake_runner.fail_with = RunnerError("docker exploded")
    response = client.post("/v1/execute", json={"language": "python", "code": "x"})
    assert response.status_code == 500
    assert response.json()["error"] == {"code": "runner_error", "message": "docker exploded"}


def test_unexpected_exception_is_masked(client: TestClient, fake_runner: FakeRunner) -> None:
    fake_runner.fail_with = ZeroDivisionError("secret detail")
    client_no_raise = TestClient(client.app, raise_server_exceptions=False)
    response = client_no_raise.post("/v1/execute", json={"language": "python", "code": "x"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret" not in response.text


def test_not_found_is_structured(client: TestClient) -> None:
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_api_key_gate(fake_runner: FakeRunner) -> None:
    settings = make_settings(api_keys="k1, k2")
    assert settings.api_keys == ["k1", "k2"]
    with TestClient(create_app(settings, runner=fake_runner)) as client:
        response = client.post("/v1/execute", json={"language": "python", "code": "x"})
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["error"]["code"] == "unauthorized"

        response = client.post(
            "/v1/execute",
            json={"language": "python", "code": "x"},
            headers={"Authorization": "Bearer wrong"},
        )
        assert response.status_code == 401

        response = client.post(
            "/v1/execute",
            json={"language": "python", "code": "x"},
            headers={"Authorization": "Bearer k2"},
        )
        assert response.status_code == 200
        # Read-only endpoints stay open.
        assert client.get("/v1/languages").status_code == 200
        assert client.get("/health").status_code == 200


def test_rate_limit(fake_runner: FakeRunner) -> None:
    settings = make_settings(rate_limit="2/minute")
    with TestClient(create_app(settings, runner=fake_runner)) as client:
        for _ in range(2):
            assert (
                client.post("/v1/execute", json={"language": "python", "code": "x"}).status_code
                == 200
            )
        response = client.post("/v1/execute", json={"language": "python", "code": "x"})
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "rate_limited"
        assert int(response.headers["retry-after"]) >= 1
        # Other clients (by X-Forwarded-For) are not affected unless trust_proxy is on.
        response = client.post(
            "/v1/execute",
            json={"language": "python", "code": "x"},
            headers={"X-Forwarded-For": "10.0.0.9"},
        )
        assert response.status_code == 429


def test_rate_limit_trusts_proxy_header(fake_runner: FakeRunner) -> None:
    settings = make_settings(rate_limit="1/minute", trust_proxy=True)
    with TestClient(create_app(settings, runner=fake_runner)) as client:
        assert (
            client.post("/v1/execute", json={"language": "python", "code": "x"}).status_code == 200
        )
        response = client.post(
            "/v1/execute",
            json={"language": "python", "code": "x"},
            headers={"X-Forwarded-For": "10.0.0.9, 10.0.0.1"},
        )
        assert response.status_code == 200


def test_global_rate_limit_applies_across_clients(fake_runner: FakeRunner) -> None:
    settings = make_settings(rate_limit=None, global_rate_limit="2/minute", trust_proxy=True)
    with TestClient(create_app(settings, runner=fake_runner)) as client:
        for ip in ("10.0.0.1", "10.0.0.2"):
            response = client.post(
                "/v1/execute",
                json={"language": "python", "code": "x"},
                headers={"X-Forwarded-For": ip},
            )
            assert response.status_code == 200
        response = client.post(
            "/v1/execute",
            json={"language": "python", "code": "x"},
            headers={"X-Forwarded-For": "10.0.0.3"},
        )
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "rate_limited"
        assert "global limit" in response.json()["error"]["message"]
        assert int(response.headers["retry-after"]) >= 1


def test_client_ip_header_takes_precedence(fake_runner: FakeRunner) -> None:
    settings = make_settings(
        rate_limit="1/minute", trust_proxy=True, client_ip_header="CF-Connecting-IP"
    )
    body = {"language": "python", "code": "x"}
    with TestClient(create_app(settings, runner=fake_runner)) as client:
        headers = {"X-Forwarded-For": "1.1.1.1", "CF-Connecting-IP": "203.0.113.7"}
        assert client.post("/v1/execute", json=body, headers=headers).status_code == 200
        # Same real client, different XFF: still limited (keyed on the header).
        headers["X-Forwarded-For"] = "2.2.2.2"
        assert client.post("/v1/execute", json=body, headers=headers).status_code == 429
        # A different real client is not.
        headers["CF-Connecting-IP"] = "203.0.113.8"
        assert client.post("/v1/execute", json=body, headers=headers).status_code == 200


def test_list_settings_parse_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env vars are comma-separated strings, never JSON (this is what compose passes)."""
    from glimpse.config import Settings

    monkeypatch.setenv("GLIMPSE_CORS_ORIGINS", "*")
    monkeypatch.setenv("GLIMPSE_API_KEYS", "")
    monkeypatch.setenv("GLIMPSE_GLOBAL_RATE_LIMIT", "")
    monkeypatch.setenv("GLIMPSE_TRUST_PROXY", "false")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["*"]
    assert settings.api_keys == []
    assert settings.global_rate_limit is None
    assert settings.trust_proxy is False

    monkeypatch.setenv("GLIMPSE_CORS_ORIGINS", "https://a.example, https://b.example")
    monkeypatch.setenv("GLIMPSE_API_KEYS", "k1,k2")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["https://a.example", "https://b.example"]
    assert settings.api_keys == ["k1", "k2"]


def test_rate_limit_can_be_disabled() -> None:
    assert make_settings(rate_limit="off").rate_limit is None
    assert make_settings(rate_limit="").rate_limit is None
    assert make_settings(rate_limit="100/hour").rate_limit == "100/hour"
    assert make_settings(global_rate_limit="").global_rate_limit is None
    assert make_settings(client_ip_header="none").client_ip_header is None


def test_cors_preflight(client: TestClient) -> None:
    response = client.options(
        "/v1/execute",
        headers={
            "Origin": "https://glimpse.daviskeene.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"


def test_openapi_documents_errors(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    execute = spec["paths"]["/v1/execute"]["post"]
    assert set(execute["responses"]) >= {"200", "400", "413", "422", "429", "503"}
    assert "ExecuteResponse" in spec["components"]["schemas"]


def test_lifespan_stops_runner(fake_runner: FakeRunner, settings: object) -> None:
    app = create_app(make_settings(), runner=fake_runner)
    with TestClient(app):
        assert fake_runner.started
        assert not fake_runner.stopped
    assert fake_runner.stopped
