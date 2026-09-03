"""Run code as a plain subprocess on the API host. **No isolation.**

Only for tests and for trusted, single-user setups where you explicitly opt in
with ``GLIMPSE_RUNNER=unsafe-local``. The name is deliberately unpleasant.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any

from ..config import Settings
from ..execution import ExecutionResult, execute_local
from ..languages import LANGUAGES, Language
from .base import Runner, parse_version_output

log = logging.getLogger("glimpse.local")


class UnsafeLocalRunner(Runner):
    name = "unsafe-local"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._versions: dict[str, str] | None = None

    async def start(self) -> None:
        log.warning(
            "unsafe-local runner selected: user code runs directly on this host with no isolation"
        )

    async def execute(
        self, language: Language, code: str, *, stdin: str, timeout_s: float
    ) -> ExecutionResult:
        return await asyncio.to_thread(
            execute_local,
            language,
            code,
            stdin=stdin,
            timeout_s=timeout_s,
            max_output_bytes=self.settings.max_output_bytes,
        )

    async def health(self) -> dict[str, Any]:
        return {"isolation": "none"}

    async def versions(self) -> dict[str, str]:
        if self._versions is None:
            self._versions = await asyncio.to_thread(_probe_versions)
        return self._versions


def _probe_versions() -> dict[str, str]:
    found: dict[str, str] = {}
    for lang in LANGUAGES:
        if not lang.version:
            continue
        try:
            proc = subprocess.run(
                list(lang.version), capture_output=True, text=True, timeout=20, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        version = parse_version_output(proc.stdout, proc.stderr)
        if version:
            found[lang.id] = version
    return found
