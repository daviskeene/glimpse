"""Docker sandbox runner.

Each execution gets its own ephemeral container created from the ``glimpse-sandbox``
image with every hardening knob Docker offers turned on (see ``_create_container``),
and the container is destroyed afterwards -- nothing is ever reused between two
requests. A small warm pool hides the container start-up latency.

All docker-py calls are blocking, so they run on the runner's own thread pool (see
``_call``); the event loop is never blocked. An ``AdmissionGate`` bounds how many runs
are in flight and queues a short burst instead of refusing it.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import functools
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, TypeVar

import docker
from docker.errors import APIError, DockerException, ImageNotFound, NotFound
from docker.models.containers import Container
from docker.types import Ulimit

from ..config import Settings
from ..execution import (
    KILLED_EXIT_CODE,
    ExecutionResult,
    Phase,
    RunnerError,
    annotate_kill,
    decode_output,
)
from ..languages import LANGUAGES, Language, render, render_env
from ..source import prepare
from .admission import AdmissionGate
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
# Seconds stop() lets in-progress pool refills finish (so their containers are disposed of
# here rather than racing the final sweep) before cancelling the refill task.
REFILL_STOP_GRACE_S = 30.0

T = TypeVar("T")


def _ms(seconds: float) -> int:
    return int(seconds * 1000)


@dataclass(slots=True)
class _Progress:
    """Which phase the worker thread is in, so the async backstop can attribute a kill."""

    phase: Phase = "run"


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
        self._gate = AdmissionGate(
            settings.sandbox_max_concurrency,
            queue_size=settings.sandbox_queue_size,
            queue_timeout_s=settings.sandbox_queue_timeout_s,
        )
        self._creating = 0
        self._stopped = True
        self._executor: ThreadPoolExecutor | None = None
        self._versions: dict[str, str] | None = None
        self._versions_lock = asyncio.Lock()

    # --- lifecycle ----------------------------------------------------------------

    async def start(self) -> None:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._thread_count(), thread_name_prefix="glimpse-docker"
            )
        if self._client is None:
            try:
                self._client = await self._call(docker.from_env, timeout=180)
            except DockerException as exc:
                raise RunnerError(f"cannot connect to the Docker daemon: {exc}") from exc
        image = self.settings.sandbox_image
        try:
            await self._call(self._client.images.get, image)
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
            "docker runner ready (image=%s pool=%d max_concurrency=%d queue=%d/%.1fs "
            "threads=%d mem=%dMiB cpus=%s pids=%d)",
            image,
            self.settings.sandbox_pool_size,
            self.settings.sandbox_max_concurrency,
            self.settings.sandbox_queue_size,
            self.settings.sandbox_queue_timeout_s,
            self._thread_count(),
            self.settings.sandbox_memory_mb,
            self.settings.sandbox_cpus,
            self.settings.sandbox_pids_limit,
        )

    async def stop(self) -> None:
        if self._stopped and self._client is None:
            self._shutdown_executor()
            return
        self._stopped = True
        self._wake.set()  # the refill loop exits as soon as it sees _stopped
        if self._refill_task is not None:
            try:
                await asyncio.wait_for(self._refill_task, timeout=REFILL_STOP_GRACE_S)
            except TimeoutError:
                # wait_for cancelled the task; the final sweep catches anything it leaked.
                log.warning("pool refill did not finish in %.0fs", REFILL_STOP_GRACE_S)
            except Exception:
                log.exception("pool refill failed during stop")
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
        self._shutdown_executor()

    def _shutdown_executor(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None

    def _thread_count(self) -> int:
        s = self.settings
        # One thread per in-flight run (held for the whole run), plus concurrent refills,
        # disposals (up to one per finished run) and the odd health / version probe.
        return min(64, max(8, 2 * s.sandbox_max_concurrency + s.sandbox_refill_concurrency + 4))

    async def _call(self, fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
        """Run a blocking docker-py call on the runner's own thread pool.

        ``asyncio.to_thread`` would use the loop's default executor, which has only
        ``cpu_count + 4`` threads (six on a two-vCPU host). Every in-flight run holds a
        thread for its whole duration, so on that shared pool a few concurrent runs starve
        the refills and disposals that keep the sandbox pool warm.
        """
        if self._executor is None:
            return await asyncio.to_thread(fn, *args, **kwargs)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, functools.partial(fn, *args, **kwargs))

    async def health(self) -> dict[str, Any]:
        if self._client is None or self._stopped:
            raise RunnerError("docker runner is not running")
        try:
            await self._call(self._client.ping)
        except DockerException as exc:
            raise RunnerError(f"docker daemon unreachable: {exc}") from exc
        return {
            "image": self.settings.sandbox_image,
            "pool_ready": self._pool.qsize(),
            "pool_size": self.settings.sandbox_pool_size,
            "in_flight": self._gate.in_flight,
            "queued": self._gate.queued,
            "max_concurrency": self.settings.sandbox_max_concurrency,
            "queue_size": self.settings.sandbox_queue_size,
            "queue_timeout_s": self.settings.sandbox_queue_timeout_s,
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
        timings: dict[str, int] = {}
        async with self._gate.slot() as waited_s:
            timings["queue"] = _ms(waited_s)
            started = time.monotonic()
            container, pool_hit = await self._acquire()
            timings["acquire"] = _ms(time.monotonic() - started)
            if not pool_hit:
                timings["create"] = timings["acquire"]  # the pool was empty: a cold start
            try:
                budget = timeout_s + BACKSTOP_GRACE_S
                if language.compile is not None:
                    budget += language.compile_timeout_s
                progress = _Progress()
                try:
                    result = await asyncio.wait_for(
                        self._call(
                            self._run,
                            container,
                            language,
                            code,
                            stdin,
                            timeout_s,
                            progress,
                            timings,
                        ),
                        timeout=budget,
                    )
                except DockerException as exc:
                    raise RunnerError(f"sandbox execution failed: {exc}") from exc
                except TimeoutError:
                    log.error("backstop hit: killing sandbox %s", container.short_id)
                    await self._call(self._kill, container)
                    result = ExecutionResult(
                        language=language.id,
                        phase=progress.phase,
                        exit_code=KILLED_EXIT_CODE,
                        timed_out=True,
                        stdout="",
                        stderr="[glimpse] execution exceeded the hard time limit and was killed.\n",
                        duration_ms=int(budget * 1000),
                    )
                result.timings = timings
                return result
            finally:
                self._dispose(container)

    async def versions(self) -> dict[str, str]:
        async with self._versions_lock:
            if self._versions is None:
                if self._client is None or self._stopped:
                    raise RunnerError("docker runner is not running")
                container, _ = await self._acquire()
                try:
                    self._versions = await self._call(self._probe_versions, container)
                finally:
                    self._dispose(container)
            return self._versions

    # --- pool ---------------------------------------------------------------------

    async def _acquire(self) -> tuple[Container, bool]:
        """A warm container from the pool (``True``) or, if it is empty, a new one (``False``)."""
        try:
            container = self._pool.get_nowait()
        except asyncio.QueueEmpty:
            container = None
        self._wake.set()
        if container is not None:
            return container, True
        try:
            return await self._call(self._create_container), False
        except DockerException as exc:
            raise RunnerError(f"could not create sandbox container: {exc}") from exc

    async def _refill_loop(self) -> None:
        """Keep ``sandbox_pool_size`` warm containers ready.

        Up to ``sandbox_refill_concurrency`` are created at once: one at a time caps the
        refill rate at roughly 1 / create-time, and above that request rate every run
        would pay a cold start.
        """
        target = self.settings.sandbox_pool_size
        parallel = max(1, self.settings.sandbox_refill_concurrency)
        while not self._stopped:
            try:
                deficit = target - self._pool.qsize() - self._creating
                if deficit > 0:
                    n = min(deficit, parallel)
                    self._creating += n
                    try:
                        created = await asyncio.gather(
                            *(self._call(self._create_container) for _ in range(n)),
                            return_exceptions=True,
                        )
                    finally:
                        self._creating -= n
                    failed = False
                    for item in created:
                        if isinstance(item, BaseException):
                            failed = True
                            log.error("failed to create a sandbox container: %s", item)
                        elif self._is_stopped():
                            # stop() ran while we were creating: don't leak the container.
                            self._dispose(item)
                        else:
                            await self._pool.put(item)
                    if failed:
                        await asyncio.sleep(1.0)
                    continue
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("sandbox pool refill failed; retrying shortly")
                await asyncio.sleep(1.0)
                continue
            self._wake.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=5.0)

    def _is_stopped(self) -> bool:
        # Method rather than attribute so type narrowing across `await` doesn't hide it.
        return self._stopped

    def _dispose(self, container: Container) -> None:
        task = asyncio.create_task(self._call(self._remove, container))
        self._disposals.add(task)
        task.add_done_callback(self._disposals.discard)

    async def _sweep(self) -> None:
        """Remove every sandbox container on the daemon (leaks from a previous process)."""
        assert self._client is not None
        removed = await self._call(self._sweep_sync)
        if removed:
            log.warning("removed %d leftover sandbox container(s)", removed)

    def _sweep_sync(self) -> int:
        assert self._client is not None
        count = 0
        # sparse=True: don't inspect each container after listing it; one that another
        # process (or this one's disposals) is removing at the same time would 404.
        for container in self._client.containers.list(
            all=True, sparse=True, filters={"label": f"{LABEL}=1"}
        ):
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
        self,
        container: Container,
        language: Language,
        code: str,
        stdin: str,
        timeout_s: float,
        progress: _Progress | None = None,
        timings: dict[str, int] | None = None,
    ) -> ExecutionResult:
        """Upload, compile, run (on a worker thread). Phase wall times land in ``timings``."""
        progress = progress or _Progress()
        timings = timings if timings is not None else {}
        prepared = prepare(language, code)
        src = f"{WORK}/{prepared.filename}"
        out = f"{WORK}/{language.artifact or 'main'}"
        stem = prepared.stem
        env = self._environment(language)
        started = time.monotonic()
        self._upload(
            container,
            {prepared.filename: prepared.code.encode("utf-8"), "stdin": stdin.encode("utf-8")},
        )
        timings["upload"] = _ms(time.monotonic() - started)

        compile_stderr = ""
        if language.compile is not None:
            progress.phase = "compile"
            argv = render(language.compile, work=WORK, tmp=TMP, src=src, out=out, stem=stem)
            started = time.monotonic()
            outcome = self._exec(
                container, argv, env, timeout_s=language.compile_timeout_s, stdin_file=None
            )
            timings["compile"] = _ms(time.monotonic() - started)
            if outcome.exit_code != 0 or outcome.timed_out:
                result = self._to_result(language, "compile", outcome)
                annotate_kill(
                    result,
                    memory_mb=self.settings.sandbox_memory_mb,
                    pids_limit=self.settings.sandbox_pids_limit,
                )
                return result
            compile_stderr = decode_output(outcome.stderr)

        progress.phase = "run"
        argv = render(language.run, work=WORK, tmp=TMP, src=src, out=out, stem=stem)
        started = time.monotonic()
        outcome = self._exec(container, argv, env, timeout_s=timeout_s, stdin_file=STDIN_FILE)
        timings["run"] = _ms(time.monotonic() - started)
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
            # Both the payload and the target path travel as env vars: file names derived
            # from user code (Java class names may contain `$`) must never be interpolated
            # into shell text.
            env[f"GLIMPSE_F{idx}"] = chunk
            env[f"GLIMPSE_T{idx}"] = target
            op = ">>" if append else ">"
            script.append(f'printf %s "${{GLIMPSE_F{idx}}}" | base64 -d {op} "${{GLIMPSE_T{idx}}}"')
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
        watchdog_fired = threading.Event()

        def _watchdog_kill() -> None:
            watchdog_fired.set()
            self._kill(container)

        watchdog = threading.Timer(timeout_s + WATCHDOG_GRACE_S, _watchdog_kill)
        watchdog.daemon = True
        # exec_start performs the HTTP request eagerly, so once it returns the process is
        # running; starting the clock and the watchdog here keeps daemon latency from
        # eating into the grace window (a slow start must not read as a timeout).
        stream = api.exec_start(exec_id, stream=True, demux=True)
        started = time.monotonic()
        watchdog.start()

        out = bytearray()
        err = bytearray()
        out_total = err_total = 0
        truncated = False
        aborted = False
        try:
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
        except (OSError, DockerException):
            # Killing the container (flood abort, watchdog) can tear the exec stream down
            # under us; that is the expected end of this exec, not a backend failure.
            if not (aborted or watchdog_fired.is_set()):
                raise
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
        if watchdog_fired.is_set() and not aborted:
            # Something (e.g. a setsid'd child holding the exec pipes) kept the stream open
            # past the deadline and the watchdog killed the container: that is a timeout,
            # whatever exit code the daemon reports for the interrupted exec.
            timed_out = True
            note = b"[glimpse] the sandbox did not finish by the deadline and was killed.\n"
            err = bytearray(err[: max(0, cap - len(note))]) + note
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
