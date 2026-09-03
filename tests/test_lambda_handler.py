from __future__ import annotations

import lambda_handler


def test_handler_runs_python() -> None:
    result = lambda_handler.handler(
        {"language": "py", "code": "print(input()[::-1])", "stdin": "abc"}, None
    )
    assert result["language"] == "python"
    assert result["phase"] == "run"
    assert result["exit_code"] == 0
    assert result["stdout"] == "cba\n"
    assert result["timed_out"] is False
    assert set(result) == {
        "language",
        "phase",
        "exit_code",
        "timed_out",
        "stdout",
        "stderr",
        "duration_ms",
        "truncated",
        "compile_stderr",
    }


def test_handler_timeout_is_clamped_and_reported() -> None:
    result = lambda_handler.handler(
        {"language": "python", "code": "while True: pass", "timeout_s": 0.01}, None
    )
    assert result["timed_out"] is True
    assert result["exit_code"] == 137
    assert result["duration_ms"] >= 900  # clamped up to 1s


def test_handler_errors() -> None:
    assert lambda_handler.handler({"language": "cobol", "code": "x"}, None)["error"]["code"] == (
        "unsupported_language"
    )
    assert lambda_handler.handler({"language": "python"}, None)["error"]["code"] == (
        "validation_error"
    )


def test_handler_actions() -> None:
    assert lambda_handler.handler({"action": "ping"}, None) == {"ok": True}
    versions = lambda_handler.handler({"action": "versions"}, None)["versions"]
    assert versions["python"].startswith("Python 3")


def test_legacy_alias() -> None:
    assert lambda_handler.lambda_handler is lambda_handler.handler
