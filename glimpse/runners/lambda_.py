"""AWS Lambda runner: invokes the Glimpse Lambda image (see ``lambda/``).

The function itself runs ``glimpse.execution.execute_local`` inside the Lambda
micro-VM, so this runner is a thin, non-blocking wrapper around ``boto3``'s
``invoke`` with retries disabled (a retry would run the user's code twice).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from ..config import Settings
from ..execution import ExecutionResult, RunnerError
from ..languages import Language
from .base import Runner

log = logging.getLogger("glimpse.lambda")


class LambdaRunner(Runner):
    name = "lambda"

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        self._client: Any | None = client
        self._versions: dict[str, str] | None = None

    async def start(self) -> None:
        if not self.settings.lambda_function_name:
            raise RunnerError("GLIMPSE_LAMBDA_FUNCTION_NAME is required for the lambda runner")
        if self._client is None:
            self._client = await asyncio.to_thread(self._make_client)
        log.info("lambda runner ready (function=%s)", self.settings.lambda_function_name)

    def _make_client(self) -> Any:
        import boto3
        from botocore.config import Config

        config = Config(
            connect_timeout=5,
            read_timeout=int(self.settings.max_timeout_s) + 120,
            retries={"max_attempts": 0},
        )
        return boto3.client("lambda", region_name=self.settings.aws_region, config=config)

    async def execute(
        self, language: Language, code: str, *, stdin: str, timeout_s: float
    ) -> ExecutionResult:
        payload = {
            "language": language.id,
            "code": code,
            "stdin": stdin,
            "timeout_s": timeout_s,
            "max_output_bytes": self.settings.max_output_bytes,
        }
        data = await asyncio.to_thread(self._invoke, payload)
        if "error" in data:
            err = data["error"]
            raise RunnerError(f"lambda returned an error: {err.get('message', err)}")
        try:
            return ExecutionResult(
                language=str(data["language"]),
                phase="compile" if data["phase"] == "compile" else "run",
                exit_code=int(data["exit_code"]),
                timed_out=bool(data["timed_out"]),
                stdout=str(data["stdout"]),
                stderr=str(data["stderr"]),
                duration_ms=int(data["duration_ms"]),
                truncated=bool(data.get("truncated", False)),
                compile_stderr=str(data.get("compile_stderr", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RunnerError(f"unexpected payload from lambda: {exc}") from exc

    async def health(self) -> dict[str, Any]:
        if self._client is None:
            raise RunnerError("lambda runner is not running")
        return {"function": self.settings.lambda_function_name, "region": self.settings.aws_region}

    async def versions(self) -> dict[str, str]:
        if self._versions is None:
            data = await asyncio.to_thread(self._invoke, {"action": "versions"})
            versions = data.get("versions", {})
            self._versions = {str(k): str(v) for k, v in versions.items()}
        return self._versions

    def _invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self._client is not None
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            response = self._client.invoke(
                FunctionName=self.settings.lambda_function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload).encode("utf-8"),
            )
        except (BotoCoreError, ClientError) as exc:
            raise RunnerError(f"lambda invoke failed: {exc}") from exc
        raw = response["Payload"].read()
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise RunnerError("lambda returned a non-JSON payload") from exc
        if response.get("FunctionError"):
            message = data.get("errorMessage", raw[:500]) if isinstance(data, dict) else raw[:500]
            raise RunnerError(f"lambda function error: {message}")
        if not isinstance(data, dict):
            raise RunnerError("lambda returned an unexpected payload type")
        return data
