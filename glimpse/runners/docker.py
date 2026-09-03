"""Docker sandbox runner.

Each execution gets its own ephemeral container created from the ``glimpse-sandbox``
image with every hardening knob Docker offers turned on (see ``_create_container``),
and the container is destroyed afterwards -- nothing is ever reused between two
requests. A small warm pool hides the container start-up latency.

All docker-py calls are blocking, so they run on worker threads via
``asyncio.to_thread``; the event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import docker
from docker.errors import APIError, DockerException, ImageNotFound, NotFound
from docker.models.containers import Container
from docker.types import Ulimit

from ..config import Settings
from ..execution import (
    KILLED_EXIT_CODE,
    ExecutionResult,
    NoCapacityError,
    RunnerError,
    annotate_kill,
    decode_output,
)
from ..languages import LANGUAGES, Language, render, render_env
from ..source import prepare
from .base import Runner, parse_version_output

log = logging.getLogger("glimpse.docker")

LABEL = "glimpse.sandbox"
WORK = "/work"
TMP = "/tmp"  # noqa: S108 - path inside the container
STDIN_FILE = f"{WORK}/stdin"
# Exit status glimpse-run (the in-sandbox supervisor) uses when it killed the process
# group because the deadline passed.
SUPERVISOR_TIMEOUT_EXIT = 124
# Base64 characters per environment string / per upload exec (see `_upload`).
UPLOAD_CHUNK_CHARS = 96 * 1024
UPLOAD_BATCH_CHARS = 1024 * 1024
# Seconds after the in-container `timeout` at which a watchdog thread kills the
# container outright (covers orphaned children keeping the exec's pipes open).
WATCHDOG_GRACE_S = 2.0
# Extra seconds the async backstop waits beyond that before giving up on the thread.
BACKSTOP_GRACE_S = 10.0


@dataclass(slots=True)
class _ExecOutcome:
    exit_code: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    truncated: bool
    duration_ms: int


class DockerRunner(Runner):
    name = "docker"

    def __init__(self, settings: Settings, client: docker.DockerClient | None = None) -> None:
        self.settings = settings
        self._client = client
        self._pool: asyncio.Queue[Container] = asyncio.Queue()
        self._wake = asyncio.Event()
        self._refill_task: asyncio.Task[None] | None = None
        self._disposals: set[asyncio.Task[None]] = set()
        self._in_flight = 0
        self._creating = 0
        self._stopped = True
        self._versions: dict[str, str] | None = None

    # --- lifecycle ----------------------------------------------------------------

    async def start(self) -> None:
        if self._client is None:
            try:
                self._client = await asyncio.to_thread(docker.from_env, timeout=180)
            except DockerException as exc:
                raise RunnerError(f"cannot connect to the Docker daemon: {exc}") from exc
        image = self.settings.sandbox_image
        try:
            await asyncio.to_thread(self._client.images.get, image)
        except ImageNotFound:
            raise RunnerError(
                f"sandbox image {image!r} not found; build it with `make sandbox` "
                f"(docker build -t {image} sandbox/)"
            ) from None
        except DockerException as exc:
            raise RunnerError(f"cannot inspect sandbox image {image!r}: {exc}") from exc
        await self._sweep()
        self._stopped = False
        if self.settings.sandbox_pool_size > 0:
            self._refill_task = asyncio.create_task(self._refill_loop(), name="glimpse-refill")
        log.info(
            "docker runner ready (image=%s pool=%d max_concurrency=%d mem=%dMiB cpus=%s pids=%d)",
            image,
            self.settings.sandbox_pool_size,
            self.settings.sandbox_max_concurrency,
            self.settings.sandbox_memory_mb,
            self.settings.sandbox_cpus,
            self.settings.sandbox_pids_limit,
        )

    async def stop(self) -> None:
        if self._stopped and self._client is None:
            return
        self._stopped = True
        if self._refill_task is not None:
            self._refill_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._refill_task
            self._refill_task = None
        while True:
            try:
                container = self._pool.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._dispose(container)
        if self._disposals:
            await asyncio.gather(*self._disposals, return_exceptions=True)
        await self._sweep()

    async def health(self) -> dict[str, Any]:
        if self._client is None or self._stopped:
            raise RunnerError("docker runner is not running")
        try:
            await asyncio.to_thread(self._client.ping)
        except DockerException as exc:
            raise RunnerError(f"docker daemon unreachable: {exc}") from exc
        return {
            "image": self.settings.sandbox_image,
            "pool_ready": self._pool.qsize(),
            "pool_size": self.settings.sandbox_pool_size,
            "in_flight": self._in_flight,
            "max_concurrency": self.settings.sandbox_max_concurrency,
            "limits": {
                "memory_mb": self.settings.sandbox_memory_mb,
                "cpus": self.settings.sandbox_cpus,
                "pids": self.settings.sandbox_pids_limit,
                "tmpfs_mb": self.settings.sandbox_tmpfs_mb,
                "network": "none",
            },
        }

    # --- execution ----------------------------------------------------------------

    async def execute(
        self, language: Language, code: str, *, stdin: str, timeout_s: float
    ) -> ExecutionResult:
        if self._client is None or self._stopped:
            raise RunnerError("docker runner is not running")
        if self._in_flight >= self.settings.sandbox_max_concurrency:
            raise NoCapacityError(
                f"at capacity ({self.settings.sandbox_max_concurrency} concurrent executions)"
            )
        self._in_flight += 1
        try:
            container = await self._acquire()
            try:
                budget = timeout_s + BACKSTOP_GRACE_S
                if language.compile is not None:
                    budget += language.compile_timeout_s
                try:
                    return await asyncio.wait_for(
                        asyncio.to_thread(self._run, container, language, code, stdin, timeout_s),
                        timeout=budget,
                    )
                except TimeoutError:
                    log.error("backstop hit: killing sandbox %s", container.short_id)
                    await asyncio.to_thread(self._kill, container)
                    return ExecutionResult(
                        language=language.id,
                        phase="run",
                        exit_code=KILLED_EXIT_CODE,
                        timed_out=True,
                        stdout="",
                        stderr="[glimpse] execution exceeded the hard time limit and was killed.\n",
                        duration_ms=int(budget * 1000),
                    )
            finally:
                self._dispose(container)
        finally:
            self._in_flight -= 1

    async def versions(self) -> dict[str, str]:
        if self._versions is None:
            if self._client is None or self._stopped:
                raise RunnerError("docker runner is not running")
            container = await self._acquire()
            try:
                self._versions = await asyncio.to_thread(self._probe_versions, container)
            finally:
                self._dispose(container)
        return self._versions

    # --- pool ---------------------------------------------------------------------

    async def _acquire(self) -> Container:
        try:
            container = self._pool.get_nowait()
        except asyncio.QueueEmpty:
            container = None
        self._wake.set()
        if container is not None:
            return container
        try:
            return await asyncio.to_thread(self._create_container)
        except DockerException as exc:
            raise RunnerError(f"could not create sandbox container: {exc}") from exc

    async def _refill_loop(self) -> None:
        target = self.settings.sandbox_pool_size
        while not self._stopped:
            try:
                while not self._stopped and self._pool.qsize() + self._creating < target:
                    self._creating += 1
                    try:
                        container = await asyncio.to_thread(self._create_container)
                    finally:
                        self._creating -= 1
                    if self._is_stopped():
                        # stop() ran while we were creating: don't leak the container.
                        self._dispose(container)
                        break
                    await self._pool.put(container)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("failed to create a sandbox container; retrying shortly")
                await asyncio.sleep(1.0)
                continue
            self._wake.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=5.0)

    def _is_stopped(self) -> bool:
        # Method rather than attribute so type narrowing across `await` doesn't hide it.
        return self._stopped

    def _dispose(self, container: Container) -> None:
        task = asyncio.create_task(asyncio.to_thread(self._remove, container))
        self._disposals.add(task)
        task.add_done_callback(self._disposals.discard)

    async def _sweep(self) -> None:
        """Remove every sandbox container on the daemon (leaks from a previous process)."""
        assert self._client is not None
        removed = await asyncio.to_thread(self._sweep_sync)
        if removed:
            log.warning("removed %d leftover sandbox container(s)", removed)

    def _sweep_sync(self) -> int:
        assert self._client is not None
        count = 0
        for container in self._client.containers.list(all=True, filters={"label": f"{LABEL}=1"}):
            self._remove(container)
            count += 1
        return count

    # --- blocking helpers (run on worker threads) ----------------------------------

    def _create_container(self) -> Container:
        assert self._client is not None
        s = self.settings
        mem = f"{s.sandbox_memory_mb}m"
        # NB: Docker mounts tmpfs *noexec* by default; compiled binaries run from /work,
        # so exec must be allowed explicitly.
        tmpfs = f"rw,exec,nosuid,nodev,size={s.sandbox_tmpfs_mb}m,mode=1777"
        fsize = s.sandbox_tmpfs_mb * 1024 * 1024
        container = self._client.containers.create(
            s.sandbox_image,
            command=["sleep", "infinity"],
            detach=True,
            user=s.sandbox_user,
            working_dir=WORK,
            hostname="sandbox",
            network_mode="none",
            network_disabled=True,
            mem_limit=mem,
            memswap_limit=mem,
            nano_cpus=int(s.sandbox_cpus * 1_000_000_000),
            pids_limit=s.sandbox_pids_limit,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            read_only=True,
            tmpfs={WORK: tmpfs, TMP: tmpfs},
            init=True,
            ulimits=[
                Ulimit(name="nofile", soft=1024, hard=1024),
                Ulimit(name="core", soft=0, hard=0),
                Ulimit(name="fsize", soft=fsize, hard=fsize),
            ],
            labels={LABEL: "1"},
            environment={"HOME": WORK, "TMPDIR": TMP},
        )
        container.start()
        return container

    @staticmethod
    def _remove(container: Container) -> None:
        try:
            container.remove(force=True, v=True)
        except NotFound:
            pass
        except APIError as exc:
            log.warning("failed to remove sandbox %s: %s", container.short_id, exc)

    @staticmethod
    def _kill(container: Container) -> None:
        with contextlib.suppress(APIError):
            container.kill()

    def _environment(self, language: Language) -> dict[str, str]:
        env = {"HOME": WORK, "TMPDIR": TMP, "USER": self.settings.sandbox_user}
        env.update(render_env(language.env, work=WORK, tmp=TMP))
        return env

    def _run(
        self, container: Container, language: Language, code: str, stdin: str, timeout_s: float
    ) -> ExecutionResult:
        prepared = prepare(language, code)
        src = f"{WORK}/{prepared.filename}"
        out = f"{WORK}/{language.artifact or 'main'}"
        stem = prepared.stem
        env = self._environment(language)
        self._upload(
            container,
            {prepared.filename: prepared.code.encode("utf-8"), "stdin": stdin.encode("utf-8")},
        )

        compile_stderr = ""
        if language.compile is not None:
            argv = render(language.compile, work=WORK, tmp=TMP, src=src, out=out, stem=stem)
            outcome = self._exec(
                container, argv, env, timeout_s=language.compile_timeout_s, stdin_file=None
            )
            if outcome.exit_code != 0 or outcome.timed_out:
                result = self._to_result(language, "compile", outcome)
                annotate_kill(
                    result,
                    memory_mb=self.settings.sandbox_memory_mb,
                    pids_limit=self.settings.sandbox_pids_limit,
                )
                return result
            compile_stderr = decode_output(outcome.stderr)

        argv = render(language.run, work=WORK, tmp=TMP, src=src, out=out, stem=stem)
        outcome = self._exec(container, argv, env, timeout_s=timeout_s, stdin_file=STDIN_FILE)
        result = self._to_result(language, "run", outcome, compile_stderr=compile_stderr)
        annotate_kill(
            result,
            memory_mb=self.settings.sandbox_memory_mb,
            pids_limit=self.settings.sandbox_pids_limit,
        )
        return result

    @staticmethod
    def _to_result(
        language: Language, phase: str, outcome: _ExecOutcome, *, compile_stderr: str = ""
    ) -> ExecutionResult:
        return ExecutionResult(
            language=language.id,
            phase="compile" if phase == "compile" else "run",
            exit_code=outcome.exit_code,
            timed_out=outcome.timed_out,
            stdout=decode_output(outcome.stdout),
            stderr=decode_output(outcome.stderr),
            duration_ms=outcome.duration_ms,
            truncated=outcome.truncated,
            compile_stderr=compile_stderr,
        )

    def _upload(self, container: Container, files: dict[str, bytes]) -> None:
        """Write ``files`` into ``/work`` as the sandbox user.

        Docker refuses ``PUT /containers/{id}/archive`` for containers with a
        read-only rootfs (even into a tmpfs), so the bytes travel base64-encoded in
        environment variables of a short ``sh`` exec and are decoded by the shell's
        builtin ``printf``. Strings are chunked to stay below the kernel's per-string
        ``execve`` limit (128 KiB) and batched to stay well below ``ARG_MAX``.
        """
        assert self._client is not None
        api = self._client.api
        parts: list[tuple[str, str, bool]] = []  # (chunk, target, append)
        for name, data in files.items():
            encoded = base64.b64encode(data).decode("ascii")
            chunks = [
                encoded[i : i + UPLOAD_CHUNK_CHARS]
                for i in range(0, len(encoded), UPLOAD_CHUNK_CHARS)
            ] or [""]
            parts.extend((chunk, f"{WORK}/{name}", idx > 0) for idx, chunk in enumerate(chunks))

        batch: list[tuple[str, str, bool]] = []
        batch_size = 0
        for part in parts:
            if batch and batch_size + len(part[0]) > UPLOAD_BATCH_CHARS:
                self._upload_batch(api, container, batch)
                batch, batch_size = [], 0
            batch.append(part)
            batch_size += len(part[0])
        if batch:
            self._upload_batch(api, container, batch)

    def _upload_batch(
        self, api: Any, container: Container, batch: list[tuple[str, str, bool]]
    ) -> None:
        env: dict[str, str] = {}
        script = ["set -e"]
        for idx, (chunk, target, append) in enumerate(batch):
            var = f"GLIMPSE_F{idx}"
            env[var] = chunk
            op = ">>" if append else ">"
            script.append(f'printf %s "${var}" | base64 -d {op} "{target}"')
        exec_id = api.exec_create(
            container.id,
            ["sh", "-c", "\n".join(script)],
            user=self.settings.sandbox_user,
            workdir=WORK,
            environment=env,
        )["Id"]
        output = api.exec_start(exec_id)
        code = api.exec_inspect(exec_id).get("ExitCode")
        if code != 0:
            raise RunnerError(
                f"failed to write files into the sandbox (exit {code}): "
                f"{decode_output(output)[:200]}"
            )

    def _exec(
        self,
        container: Container,
        argv: list[str],
        env: dict[str, str],
        *,
        timeout_s: float,
        stdin_file: str | None,
    ) -> _ExecOutcome:
        """Run ``argv`` inside the container under ``glimpse-run`` with capped output.

        ``glimpse-run`` (see ``sandbox/glimpse-run/main.go``) runs the program in its own
        process group, kills the group at the deadline (exit 124) and kills whatever the
        program left behind the moment it exits, so orphaned children can never keep the
        exec's pipes open.
        """
        assert self._client is not None
        api = self._client.api
        cap = self.settings.max_output_bytes
        cmd = ["glimpse-run", "-t", f"{timeout_s:g}"]
        if stdin_file:
            cmd += ["-i", stdin_file]
        cmd += ["--", *argv]
        exec_id = api.exec_create(
            container.id,
            cmd,
            stdout=True,
            stderr=True,
            stdin=False,
            tty=False,
            user=self.settings.sandbox_user,
            workdir=WORK,
            environment=env,
        )["Id"]
        started = time.monotonic()
        watchdog = threading.Timer(timeout_s + WATCHDOG_GRACE_S, self._kill, args=(container,))
        watchdog.daemon = True
        watchdog.start()
        stream = api.exec_start(exec_id, stream=True, demux=True)

        out = bytearray()
        err = bytearray()
        out_total = err_total = 0
        truncated = False
        aborted = False
        for chunk_out, chunk_err in stream:
            if chunk_out:
                out_total += len(chunk_out)
                room = cap - len(out)
                if room > 0:
                    out.extend(chunk_out[:room])
            if chunk_err:
                err_total += len(chunk_err)
                room = cap - len(err)
                if room > 0:
                    err.extend(chunk_err[:room])
            if out_total > cap or err_total > cap:
                truncated = True
            # Stop pumping bytes through the daemon for a program that just floods output.
            if out_total + err_total > 4 * cap:
                aborted = True
                self._kill(container)
                break
        elapsed = time.monotonic() - started
        watchdog.cancel()

        exit_code: int | None = None
        with contextlib.suppress(APIError):
            exit_code = api.exec_inspect(exec_id).get("ExitCode")
        if exit_code is None:
            exit_code = KILLED_EXIT_CODE

        # A program may itself exit with 124, so also require the deadline to have passed.
        timed_out = (
            exit_code == SUPERVISOR_TIMEOUT_EXIT and not aborted and elapsed >= timeout_s - 0.05
        )
        if timed_out:
            exit_code = KILLED_EXIT_CODE
        if aborted:
            note = f"[glimpse] output exceeded {cap} bytes; process killed.\n".encode()
            err = bytearray(err[: max(0, cap - len(note))]) + note
            exit_code = KILLED_EXIT_CODE
        return _ExecOutcome(
            exit_code=exit_code,
            stdout=bytes(out),
            stderr=bytes(err),
            timed_out=timed_out,
            truncated=truncated,
            duration_ms=int(elapsed * 1000),
        )

    def _probe_versions(self, container: Container) -> dict[str, str]:
        found: dict[str, str] = {}
        for lang in LANGUAGES:
            if not lang.version:
                continue
            try:
                outcome = self._exec(
                    container,
                    list(lang.version),
                    self._environment(lang),
                    timeout_s=30,
                    stdin_file=None,
                )
            except DockerException as exc:
                log.warning("version probe for %s failed: %s", lang.id, exc)
                continue
            version = parse_version_output(
                decode_output(outcome.stdout), decode_output(outcome.stderr)
            )
            if version:
                found[lang.id] = version
        return found
