"""AWS Lambda entry point.

Event shapes:

* ``{"language": "python", "code": "...", "stdin": "", "timeout_s": 10}`` ->
  an ``ExecutionResult`` dict (same shape as ``POST /v1/execute``).
* ``{"action": "versions"}`` -> ``{"versions": {"python": "Python 3.12.x", ...}}``
* ``{"action": "ping"}`` -> ``{"ok": true}``

Only the standard library and ``glimpse.languages`` / ``glimpse.execution`` are
imported, so the Lambda image needs no third-party packages.
"""

from __future__ import annotations

import subprocess
from typing import Any

from glimpse import languages
from glimpse.execution import DEFAULT_MAX_OUTPUT_BYTES, execute_local

MAX_TIMEOUT_S = 30.0


def _versions() -> dict[str, str]:
    found: dict[str, str] = {}
    for lang in languages.LANGUAGES:
        if not lang.version:
            continue
        try:
            proc = subprocess.run(
                list(lang.version), capture_output=True, text=True, timeout=30, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        for text in (proc.stdout, proc.stderr):
            for line in text.splitlines():
                if line.strip():
                    found[lang.id] = line.strip()[:120]
                    break
            if lang.id in found:
                break
    return found


def handler(event: dict[str, Any], context: object = None) -> dict[str, Any]:
    action = event.get("action")
    if action == "ping":
        return {"ok": True}
    if action == "versions":
        return {"versions": _versions()}

    try:
        language = languages.resolve(str(event.get("language", "")))
    except languages.UnsupportedLanguageError as exc:
        return {"error": {"code": "unsupported_language", "message": str(exc)}}
    code = event.get("code")
    if not isinstance(code, str) or not code:
        return {
            "error": {"code": "validation_error", "message": "`code` must be a non-empty string"}
        }
    stdin = event.get("stdin") or ""
    try:
        timeout_s = float(event.get("timeout_s") or 10.0)
    except (TypeError, ValueError):
        timeout_s = 10.0
    timeout_s = max(1.0, min(timeout_s, MAX_TIMEOUT_S))
    max_output = int(event.get("max_output_bytes") or DEFAULT_MAX_OUTPUT_BYTES)

    result = execute_local(
        language,
        code,
        stdin=str(stdin),
        timeout_s=timeout_s,
        max_output_bytes=max_output,
    )
    return result.to_dict()


# Backwards-compatible alias for older CMD configurations.
lambda_handler = handler
