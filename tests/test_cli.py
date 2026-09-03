from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from glimpse import cli
from glimpse.client import GlimpseClient


def _make_factory(result: dict[str, Any], seen: dict[str, Any]) -> cli.ClientFactory:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        if request.url.path == "/v1/languages":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "python",
                        "name": "Python",
                        "aliases": ["py"],
                        "version": "Python 3.12.1",
                        "compiled": False,
                        "filename": "main.py",
                        "sample": "print(1)",
                    },
                    {
                        "id": "go",
                        "name": "Go",
                        "aliases": [],
                        "version": None,
                        "compiled": True,
                        "filename": "main.go",
                        "sample": "package main",
                    },
                ],
            )
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=result)

    def factory(url: str | None, api_key: str | None) -> GlimpseClient:
        seen["url"] = url
        return GlimpseClient(url, api_key=api_key, transport=httpx.MockTransport(handler))

    return factory


def _result(**overrides: Any) -> dict[str, Any]:
    base = {
        "language": "python",
        "phase": "run",
        "exit_code": 0,
        "timed_out": False,
        "stdout": "out\n",
        "stderr": "err\n",
        "duration_ms": 12,
        "truncated": False,
    }
    base.update(overrides)
    return base


def test_run_infers_language_and_mirrors_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "hello.go"
    src.write_text("package main")
    stdin = tmp_path / "in.txt"
    stdin.write_text("data")
    seen: dict[str, Any] = {}
    factory = _make_factory(_result(language="go", exit_code=3), seen)

    code = cli.main(
        [
            "run",
            str(src),
            "--stdin-file",
            str(stdin),
            "--url",
            "http://s",
            "--api-key",
            "k",
            "-t",
            "2",
        ],
        make_client=factory,
    )
    assert code == 3
    assert seen["body"] == {
        "language": "go",
        "code": "package main",
        "stdin": "data",
        "timeout_s": 2.0,
    }
    assert seen["auth"] == "Bearer k"
    assert seen["url"] == "http://s"
    out, err = capsys.readouterr()
    assert out == "out\n"
    assert err.startswith("err\n")
    assert "[glimpse] go · run · exit 3 · 12 ms" in err


def test_run_timeout_exit_code_and_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "loop.py"
    src.write_text("while True: pass")
    factory = _make_factory(_result(timed_out=True, exit_code=137), {})
    code = cli.main(["run", str(src), "--json"], make_client=factory)
    assert code == cli.TIMEOUT_EXIT_CODE
    out, _ = capsys.readouterr()
    assert json.loads(out)["timed_out"] is True


def test_run_from_stdin_requires_lang(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = _make_factory(_result(), {})
    assert cli.main(["run", "-"], make_client=factory) == 2
    assert "cannot infer" in capsys.readouterr().err

    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("print(1)"))
    seen: dict[str, Any] = {}
    assert (
        cli.main(["run", "-", "--lang", "py", "-q"], make_client=_make_factory(_result(), seen))
        == 0
    )
    assert seen["body"]["code"] == "print(1)"


def test_run_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "/nonexistent/x.py"], make_client=_make_factory(_result(), {})) == 2
    assert "error" in capsys.readouterr().err


def test_languages_table(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["languages"], make_client=_make_factory(_result(), {})) == 0
    out = capsys.readouterr().out
    assert "python  Python (py)  Python 3.12.1" in out
    assert "go      Go" in out


def test_api_error_is_reported(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"code": "rate_limited", "message": "slow down"}})

    def factory(url: str | None, api_key: str | None) -> GlimpseClient:
        return GlimpseClient(url, transport=httpx.MockTransport(handler))

    src = tmp_path / "a.py"
    src.write_text("x")
    assert cli.main(["run", str(src)], make_client=factory) == 1
    assert "429 rate_limited: slow down" in capsys.readouterr().err


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "glimpse" in capsys.readouterr().out
