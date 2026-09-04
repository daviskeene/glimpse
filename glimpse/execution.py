"""Backend-agnostic execution primitives.

``execute_local`` runs a snippet as a subprocess on the *current* machine: a fresh
temporary working directory, a minimal environment, compile-then-run, hard
timeouts, byte-capped output and cleanup. It is used by the Lambda handler (where
the Lambda micro-VM is the isolation boundary) and by the opt-in
``unsafe-local`` runner used in tests. It intentionally depends on nothing outside
the standard library.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import IO, Any, Literal

from .languages import Language, render, render_env
from .source import prepare

Phase = Literal["compile", "run"]

DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024
# Exit code reported when a process is killed by SIGKILL (timeout, OOM, pids limit).
KILLED_EXIT_CODE = 137
# The names of host environment variables that are allowed to reach user code.
ENV_PASSTHROUGH = ("PATH", "JAVA_HOME", "GOROOT", "GOCACHE", "LD_LIBRARY_PATH")


@dataclass(slots=True)
class ExecutionResult:
    """What every backend returns. ``to_dict()`` mirrors ``models.ExecuteResponse`` 1:1."""

    language: str
    phase: Phase
    exit_code: int
    timed_out: bool
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool = False
    compile_stderr: str = ""
    timings: dict[str, int] = field(default_factory=dict, compare=False)
    """Backend phase wall times in ms (``queue``, ``acquire``, ``upload``, ``compile``, ``run``).

    Diagnostics rather than part of the result: the API surfaces them as a ``Server-Timing``
    header and in its log line, never in the JSON body.
    """

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        del data["timings"]
        return data

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class RunnerError(RuntimeError):
    """The backend itself failed (not the user's program)."""


class NoCapacityError(RunnerError):
    """The backend is saturated; the client should retry later."""


def base_environment(language: Language, *, work: str, tmp: str) -> dict[str, str]:
    """Minimal environment for user code: PATH, locale, scratch dirs, per-language extras."""
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": work,
        "TMPDIR": tmp,
        "TMP": tmp,
        "TEMP": tmp,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "USER": "sandbox",
    }
    for name in ENV_PASSTHROUGH:
        if name in os.environ and name not in env:
            env[name] = os.environ[name]
    env.update(render_env(language.env, work=work, tmp=tmp))
    return env


def decode_output(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


class _CappedReader(threading.Thread):
    """Drain a pipe on a thread, keeping at most ``cap`` bytes.

    A stream that floods far past the cap (4x) triggers ``on_flood`` once — the caller
    uses it to kill the process group so a flood cannot occupy the slot until the
    timeout — and keeps draining so the pipes still reach EOF.
    """

    def __init__(
        self, stream: IO[bytes], cap: int, on_flood: Callable[[], None] | None = None
    ) -> None:
        super().__init__(daemon=True)
        self.stream = stream
        self.cap = cap
        self.on_flood = on_flood
        self.data = bytearray()
        self.truncated = False
        self.flooded = False
        self.total = 0

    def run(self) -> None:
        try:
            while True:
                chunk = self.stream.read(65536)
                if not chunk:
                    break
                self.total += len(chunk)
                room = self.cap - len(self.data)
                if room > 0:
                    self.data.extend(chunk[:room])
                if self.total > self.cap:
                    self.truncated = True
                if self.total > 4 * self.cap and not self.flooded:
                    self.flooded = True
                    if self.on_flood is not None:
                        self.on_flood()
        except (OSError, ValueError):
            pass
        finally:
            with contextlib.suppress(OSError):
                self.stream.close()


def _feed_stdin(stream: IO[bytes], data: bytes) -> None:
    try:
        stream.write(data)
    except OSError:
        pass
    finally:
        with contextlib.suppress(OSError):
            stream.close()


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        proc.kill()


def run_process(
    argv: list[str],
    *,
    cwd: str,
    env: dict[str, str],
    stdin: bytes,
    timeout_s: float,
    max_output_bytes: int,
) -> tuple[int, bytes, bytes, bool, bool]:
    """Run one process with a group-wide SIGKILL timeout and capped output.

    Returns ``(exit_code, stdout, stderr, timed_out, truncated)``.
    """
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    on_flood = lambda: _kill_group(proc)  # noqa: E731 - tiny closure over proc
    out_reader = _CappedReader(proc.stdout, max_output_bytes, on_flood=on_flood)
    err_reader = _CappedReader(proc.stderr, max_output_bytes, on_flood=on_flood)
    out_reader.start()
    err_reader.start()
    feeder = threading.Thread(target=_feed_stdin, args=(proc.stdin, stdin), daemon=True)
    feeder.start()

    timed_out = False
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc)
        proc.wait()
    finally:
        # Whatever happened, make sure nothing from the session outlives this call.
        _kill_group(proc)

    out_reader.join(timeout=5)
    err_reader.join(timeout=5)
    feeder.join(timeout=1)

    code = proc.returncode
    if code is None or code < 0:
        # Killed by a signal: report the shell convention 128 + signal.
        code = 128 + (-code if code else signal.SIGKILL)
    err = bytes(err_reader.data)
    if (out_reader.flooded or err_reader.flooded) and not timed_out:
        # Mirror the Docker runner: a flood far past the cap is a kill, and says so.
        code = KILLED_EXIT_CODE
        note = f"[glimpse] output exceeded {max_output_bytes} bytes; process killed.\n".encode()
        err = err[: max(0, max_output_bytes - len(note))] + note
    return (
        code,
        bytes(out_reader.data),
        err,
        timed_out,
        out_reader.truncated or err_reader.truncated,
    )


def execute_local(
    language: Language,
    code: str,
    *,
    stdin: str = "",
    timeout_s: float = 10.0,
    compile_timeout_s: float | None = None,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    base_dir: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> ExecutionResult:
    """Compile (if needed) and run ``code`` as a subprocess in a throwaway directory.

    The caller is responsible for the isolation boundary around this function.
    """
    work = tempfile.mkdtemp(prefix="glimpse-", dir=base_dir)
    try:
        tmp = os.path.join(work, ".tmp")
        os.mkdir(tmp)
        prepared = prepare(language, code)
        src = os.path.join(work, prepared.filename)
        out = os.path.join(work, language.artifact or "main")
        stem = prepared.stem
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(prepared.code)
        env = base_environment(language, work=work, tmp=tmp)
        if extra_env:
            env.update(extra_env)
        stdin_bytes = stdin.encode("utf-8")

        compile_stderr = ""
        if language.compile is not None:
            argv = render(language.compile, work=work, tmp=tmp, src=src, out=out, stem=stem)
            started = time.monotonic()
            code_, c_out, c_err, c_timed_out, c_trunc = run_process(
                argv,
                cwd=work,
                env=env,
                stdin=b"",
                timeout_s=compile_timeout_s or language.compile_timeout_s,
                max_output_bytes=max_output_bytes,
            )
            elapsed = int((time.monotonic() - started) * 1000)
            if code_ != 0 or c_timed_out:
                return ExecutionResult(
                    language=language.id,
                    phase="compile",
                    exit_code=KILLED_EXIT_CODE if c_timed_out else code_,
                    timed_out=c_timed_out,
                    stdout=decode_output(c_out),
                    stderr=decode_output(c_err),
                    duration_ms=elapsed,
                    truncated=c_trunc,
                )
            compile_stderr = decode_output(c_err)

        argv = render(language.run, work=work, tmp=tmp, src=src, out=out, stem=stem)
        started = time.monotonic()
        code_, r_out, r_err, r_timed_out, r_trunc = run_process(
            argv,
            cwd=work,
            env=env,
            stdin=stdin_bytes,
            timeout_s=timeout_s,
            max_output_bytes=max_output_bytes,
        )
        elapsed = int((time.monotonic() - started) * 1000)
        return ExecutionResult(
            language=language.id,
            phase="run",
            exit_code=KILLED_EXIT_CODE if r_timed_out else code_,
            timed_out=r_timed_out,
            stdout=decode_output(r_out),
            stderr=decode_output(r_err),
            duration_ms=elapsed,
            truncated=r_trunc,
            compile_stderr=compile_stderr,
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


def annotate_kill(
    result: ExecutionResult, *, memory_mb: int | None, pids_limit: int | None
) -> None:
    """Explain an unexplained SIGKILL (exit 137 that was not a timeout) in stderr."""
    if result.exit_code != KILLED_EXIT_CODE or result.timed_out:
        return
    limits = []
    if memory_mb:
        limits.append(f"memory limit ({memory_mb} MiB)")
    if pids_limit:
        limits.append(f"process limit ({pids_limit})")
    hint = " or the ".join(limits) if limits else "a resource limit"
    note = f"[glimpse] process was killed (SIGKILL); it probably exceeded the {hint}.\n"
    sep = "\n" if result.stderr and not result.stderr.endswith("\n") else ""
    result.stderr = result.stderr + sep + note
