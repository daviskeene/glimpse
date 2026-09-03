"""The ``Runner`` interface that every backend implements."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any

from ..execution import ExecutionResult
from ..languages import Language

if TYPE_CHECKING:
    from ..config import Settings


class Runner(abc.ABC):
    """An execution backend.

    Lifecycle: ``start()`` once (may raise ``RunnerError`` if the backend is not
    usable), any number of concurrent ``execute()`` calls, then ``stop()``.
    """

    name: str = "base"

    async def start(self) -> None:  # noqa: B027 - optional hook
        """Connect, warm pools, verify prerequisites."""

    async def stop(self) -> None:  # noqa: B027 - optional hook
        """Release everything; must be safe to call twice."""

    @abc.abstractmethod
    async def execute(
        self, language: Language, code: str, *, stdin: str, timeout_s: float
    ) -> ExecutionResult:
        """Run ``code``. Program failures are *results*; backend failures raise ``RunnerError``."""

    async def health(self) -> dict[str, Any]:
        """Backend-specific status for ``GET /health``. Raise ``RunnerError`` if unhealthy."""
        return {}

    async def versions(self) -> dict[str, str]:
        """Map of language id -> toolchain version string, when the backend can tell."""
        return {}


def parse_version_output(stdout: str, stderr: str) -> str | None:
    """First meaningful line of a ``--version`` style output (java prints to stderr)."""
    for text in (stdout, stderr):
        for line in text.splitlines():
            line = line.strip()
            if line:
                return line[:120]
    return None


def create_runner(settings: Settings) -> Runner:
    """Instantiate the runner selected by ``settings.runner`` (imports lazily)."""
    if settings.runner == "docker":
        from .docker import DockerRunner

        return DockerRunner(settings)
    if settings.runner == "lambda":
        from .lambda_ import LambdaRunner

        return LambdaRunner(settings)
    if settings.runner == "unsafe-local":
        from .local import UnsafeLocalRunner

        return UnsafeLocalRunner(settings)
    raise ValueError(f"unknown runner {settings.runner!r}")
