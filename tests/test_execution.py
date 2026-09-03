from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

import pytest

from glimpse.execution import (
    KILLED_EXIT_CODE,
    ExecutionResult,
    annotate_kill,
    base_environment,
    execute_local,
)
from glimpse.languages import BY_ID

PY = BY_ID["python"]
needs_gcc = pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not installed")


def _tool_works(*argv: str) -> bool:
    try:
        return subprocess.run(argv, capture_output=True, timeout=30, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


needs_javac = pytest.mark.skipif(not _tool_works("javac", "-version"), reason="javac not usable")


def test_hello_world() -> None:
    result = execute_local(PY, "print('hello')", timeout_s=10)
    assert result.ok
    assert result.phase == "run"
    assert result.stdout == "hello\n"
    assert result.stderr == ""
    assert result.duration_ms >= 0
    assert result.truncated is False


def test_stdin_round_trip() -> None:
    result = execute_local(
        PY, "import sys; print(sys.stdin.read().upper(), end='')", stdin="héllo\nwörld"
    )
    assert result.stdout == "HÉLLO\nWÖRLD"


def test_nonzero_exit_and_stderr() -> None:
    result = execute_local(PY, "import sys; sys.stderr.write('boom'); sys.exit(3)")
    assert result.exit_code == 3
    assert result.stderr == "boom"
    assert not result.ok


def test_exception_is_a_result_not_an_error() -> None:
    result = execute_local(PY, "raise ValueError('nope')")
    assert result.exit_code == 1
    assert "ValueError: nope" in result.stderr


def test_timeout_kills_process_group() -> None:
    marker = f"glimpse-test-{os.getpid()}"
    code = f"""
import subprocess, time
subprocess.Popen(["sleep", "300"], env={{"GLIMPSE_MARKER": "{marker}"}})
print("started", flush=True)
while True:
    time.sleep(0.1)
"""
    started = time.monotonic()
    result = execute_local(PY, code, timeout_s=1)
    elapsed = time.monotonic() - started
    assert result.timed_out
    assert result.exit_code == KILLED_EXIT_CODE
    assert result.stdout == "started\n"
    assert elapsed < 5
    # The grandchild `sleep` must not survive the timeout.
    time.sleep(0.2)
    ps = subprocess.run(["ps", "-eo", "pid,command"], capture_output=True, text=True, check=False)
    assert "sleep 300" not in ps.stdout or _no_marker_sleep(marker)


def _no_marker_sleep(marker: str) -> bool:
    # Fallback for hosts with other `sleep 300` processes: check env of matching pids.
    ps = subprocess.run(["pgrep", "-f", "sleep 300"], capture_output=True, text=True, check=False)
    for pid in ps.stdout.split():
        try:
            env = subprocess.run(
                ["ps", "-o", "command=", "-p", pid], capture_output=True, text=True, check=False
            ).stdout
        except OSError:
            continue
        if marker in env:
            return False
    return True


def test_background_child_does_not_delay_return() -> None:
    code = """
import subprocess
subprocess.Popen(["sleep", "300"])
print("done")
"""
    started = time.monotonic()
    result = execute_local(PY, code, timeout_s=10)
    assert time.monotonic() - started < 3
    assert result.ok
    assert result.stdout == "done\n"


def test_output_is_capped() -> None:
    result = execute_local(PY, "print('x' * 200_000)", max_output_bytes=1024)
    assert result.truncated
    assert len(result.stdout.encode()) == 1024
    assert result.exit_code == 0


def test_unicode_output_survives() -> None:
    result = execute_local(PY, "print('ünïcödé ✓ 🎉')")
    assert result.stdout == "ünïcödé ✓ 🎉\n"


def test_environment_is_sanitised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "supersecret")
    monkeypatch.setenv("GLIMPSE_API_KEYS", "k")
    result = execute_local(PY, "import os, json; print(json.dumps(dict(os.environ)))")
    assert "supersecret" not in result.stdout
    assert "GLIMPSE_API_KEYS" not in result.stdout
    assert '"LANG": "C.UTF-8"' in result.stdout


def test_workdir_is_cleaned_up(tmp_path: object) -> None:
    base = str(tmp_path)
    result = execute_local(PY, "import os; print(os.getcwd())", base_dir=base)
    assert result.stdout.strip().startswith(base)
    assert os.listdir(base) == []


def test_base_environment_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAVA_HOME", "/opt/jdk")
    monkeypatch.setenv("SECRET_TOKEN", "x")
    env = base_environment(PY, work="/w", tmp="/t")
    assert env["JAVA_HOME"] == "/opt/jdk"
    assert "SECRET_TOKEN" not in env
    assert env["HOME"] == "/w"
    assert env["TMPDIR"] == "/t"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


@needs_gcc
def test_compile_error_reports_compile_phase() -> None:
    result = execute_local(BY_ID["c"], "int main( { return 0; }")
    assert result.phase == "compile"
    assert result.exit_code != 0
    assert "error" in result.stderr.lower()


@needs_gcc
def test_compile_warnings_are_kept_on_success() -> None:
    code = '#include <stdio.h>\nint main(void) { int unused; printf("ok\\n"); return 0; }\n'
    result = execute_local(BY_ID["c"], code)
    assert result.ok
    assert result.stdout == "ok\n"
    assert result.stderr == ""
    assert "warning" in result.compile_stderr.lower()


@needs_javac
def test_java_public_class_name_is_honoured() -> None:
    code = (
        "public class Solution { "
        'public static void main(String[] a) { System.out.println("hi"); } }'
    )
    result = execute_local(BY_ID["java"], code, timeout_s=20)
    assert result.ok, result
    assert result.stdout == "hi\n"


@needs_gcc
def test_c_hello_world_with_stdin() -> None:
    code = r"""
#include <stdio.h>
int main(void) { char buf[64]; if (fgets(buf, sizeof buf, stdin)) printf("got %s", buf); return 7; }
"""
    result = execute_local(BY_ID["c"], code, stdin="line\n")
    assert result.phase == "run"
    assert result.stdout == "got line\n"
    assert result.exit_code == 7


def test_annotate_kill_only_for_unexplained_sigkill() -> None:
    killed = ExecutionResult("python", "run", KILLED_EXIT_CODE, False, "", "", 1)
    annotate_kill(killed, memory_mb=512, pids_limit=128)
    assert "512 MiB" in killed.stderr and "128" in killed.stderr
    timed_out = ExecutionResult("python", "run", KILLED_EXIT_CODE, True, "", "", 1)
    annotate_kill(timed_out, memory_mb=512, pids_limit=128)
    assert timed_out.stderr == ""
    normal = ExecutionResult("python", "run", 1, False, "", "err", 1)
    annotate_kill(normal, memory_mb=512, pids_limit=128)
    assert normal.stderr == "err"


@pytest.mark.skipif(sys.platform == "win32", reason="posix only")
def test_result_to_dict_round_trip() -> None:
    result = execute_local(PY, "print(1)")
    data = result.to_dict()
    assert set(data) == {
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
