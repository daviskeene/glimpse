from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from glimpse.api import create_app
from glimpse.config import Settings
from glimpse.execution import ExecutionResult, NoCapacityError, RunnerError
from glimpse.languages import Language
from glimpse.runners.base import Runner


class FakeRunner(Runner):
    """Records calls and returns canned results; can be told to fail."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_with: Exception | None = None
        self.started = False
        self.stopped = False
        self.result = ExecutionResult(
            language="python",
            phase="run",
            exit_code=0,
            timed_out=False,
            stdout="hello\n",
            stderr="",
            duration_ms=7,
        )
        self.versions_map = {"python": "Python 3.99"}

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def execute(
        self, language: Language, code: str, *, stdin: str, timeout_s: float
    ) -> ExecutionResult:
        self.calls.append(
            {"language": language.id, "code": code, "stdin": stdin, "timeout_s": timeout_s}
        )
        if self.fail_with is not None:
            raise self.fail_with
        result = ExecutionResult(**self.result.to_dict())
        result.language = language.id
        return result

    async def health(self) -> dict[str, Any]:
        if isinstance(self.fail_with, RunnerError) and not isinstance(
            self.fail_with, NoCapacityError
        ):
            raise self.fail_with
        return {"fake": True}

    async def versions(self) -> dict[str, str]:
        return self.versions_map


def make_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "runner": "unsafe-local",
        "rate_limit": None,
        "api_keys": [],
        "_env_file": None,
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def fake_runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def client(settings: Settings, fake_runner: FakeRunner) -> Iterator[TestClient]:
    app = create_app(settings, runner=fake_runner)
    with TestClient(app) as test_client:
        yield test_client


def _docker_ready() -> tuple[bool, str]:
    if shutil.which("docker") is None:
        return False, "docker CLI not installed"
    try:
        image = os.environ.get("GLIMPSE_SANDBOX_IMAGE", "glimpse-sandbox")
        proc = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"docker not reachable: {exc}"
    if proc.returncode != 0:
        return False, f"sandbox image not available: {proc.stderr.strip()[:200]}"
    return True, ""


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    docker_items = [item for item in items if item.get_closest_marker("docker")]
    if not docker_items:
        return
    ready, reason = _docker_ready()
    if ready:
        return
    if os.environ.get("GLIMPSE_REQUIRE_DOCKER"):
        pytest.exit(f"GLIMPSE_REQUIRE_DOCKER is set but {reason}", returncode=1)
    marker = pytest.mark.skip(reason=reason)
    for item in docker_items:
        item.add_marker(marker)
