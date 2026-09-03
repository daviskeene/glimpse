"""Integration tests against a real Docker daemon and the glimpse-sandbox image.

Skipped automatically when Docker or the image is unavailable (set
GLIMPSE_REQUIRE_DOCKER=1 to fail instead, as CI does). Build the image with
`make sandbox` first.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from collections.abc import AsyncIterator

import pytest

from glimpse.execution import KILLED_EXIT_CODE, NoCapacityError
from glimpse.languages import BY_ID, LANGUAGES
from glimpse.runners.docker import BACKSTOP_GRACE_S, LABEL, DockerRunner
from tests.conftest import make_settings

pytestmark = pytest.mark.docker


def _sandbox_containers() -> list[str]:
    proc = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"label={LABEL}=1"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.split()


@pytest.fixture(scope="module")
async def runner() -> AsyncIterator[DockerRunner]:
    settings = make_settings(
        runner="docker",
        sandbox_pool_size=1,
        sandbox_max_concurrency=3,
        sandbox_memory_mb=512,
        sandbox_pids_limit=64,
    )
    docker_runner = DockerRunner(settings)
    await docker_runner.start()
    try:
        yield docker_runner
    finally:
        await docker_runner.stop()


@pytest.mark.parametrize("language", [lang.id for lang in LANGUAGES])
async def test_sample_program(runner: DockerRunner, language: str) -> None:
    """Every registry sample reads a name from stdin and greets it on the first line."""
    lang = BY_ID[language]
    started = time.monotonic()
    result = await runner.execute(lang, lang.sample, stdin="glimpse\n", timeout_s=10)
    elapsed = time.monotonic() - started
    assert result.ok, result
    assert result.phase == "run"
    assert result.stdout.splitlines()[0] == "hello, glimpse"
    assert result.stderr == ""
    assert result.language == language
    print(f"{language}: {elapsed:.2f}s total, {result.duration_ms} ms run")


async def test_stdin_and_unicode(runner: DockerRunner) -> None:
    code = "import sys\nfor line in sys.stdin: print(line.strip()[::-1])"
    result = await runner.execute(BY_ID["python"], code, stdin="héllo ✓\n🎉 wörld\n", timeout_s=10)
    assert result.ok
    assert result.stdout == "✓ olléh\ndlröw 🎉\n"


async def test_compile_error(runner: DockerRunner) -> None:
    result = await runner.execute(BY_ID["c"], "int main( {", stdin="", timeout_s=10)
    assert result.phase == "compile"
    assert result.exit_code != 0
    assert "error" in result.stderr
    assert not result.timed_out
    assert result.compile_stderr == ""


async def test_compile_warnings_are_kept(runner: DockerRunner) -> None:
    code = '#include <stdio.h>\nint main(void) { int unused; printf("ok\\n"); return 0; }\n'
    result = await runner.execute(BY_ID["c"], code, stdin="", timeout_s=10)
    assert result.ok, result
    assert result.stdout == "ok\n"
    assert result.stderr == ""
    assert "warning" in result.compile_stderr.lower()


async def test_java_public_class_name(runner: DockerRunner) -> None:
    code = (
        "public class Solution {\n"
        '  public static void main(String[] a) { System.out.println("solved"); }\n'
        "}\n"
    )
    result = await runner.execute(BY_ID["java"], code, stdin="", timeout_s=10)
    assert result.ok, result
    assert result.stdout == "solved\n"


async def test_java_dollar_class_and_package(runner: DockerRunner) -> None:
    dollar = (
        "public class Main$Helper { "
        'public static void main(String[] a) { System.out.println("dollar ok"); } }'
    )
    result = await runner.execute(BY_ID["java"], dollar, stdin="", timeout_s=15)
    assert result.ok, result
    assert result.stdout == "dollar ok\n"

    packaged = (
        "package com.example.demo;\n"
        "public class App { "
        'public static void main(String[] a) { System.out.println("pkg ok"); } }'
    )
    result = await runner.execute(BY_ID["java"], packaged, stdin="", timeout_s=15)
    assert result.ok, result
    assert result.stdout == "pkg ok\n"


async def test_setsid_escapee_does_not_wedge_the_slot(runner: DockerRunner) -> None:
    """A child that starts its own session (escaping glimpse-run's process-group kill) and
    keeps stdout open must not hold the request open: Docker ends the exec stream when the
    supervisor exits, and the fresh-container teardown then kills the escapee. The call
    returns promptly with the program's own result and the sandbox is immediately reusable."""
    code = (
        "import os, time, sys\n"
        "if os.fork() == 0:\n"
        "    os.setsid()\n"  # new session/pgid: survives kill(-pgid, SIGKILL)
        "    time.sleep(300)\n"  # keeps the inherited stdout fd open
        "else:\n"
        "    print('started', flush=True)\n"
        "    sys.exit(0)\n"
    )
    started = time.monotonic()
    result = await runner.execute(BY_ID["python"], code, stdin="", timeout_s=1)
    elapsed = time.monotonic() - started
    assert elapsed < 8, elapsed  # well under the async backstop; the slot is not wedged
    assert result.stdout == "started\n"
    # The sandbox is fully usable immediately afterwards.
    follow_up = await runner.execute(BY_ID["python"], "print('ok')", stdin="", timeout_s=5)
    assert follow_up.stdout == "ok\n"


async def test_go_non_main_package(runner: DockerRunner) -> None:
    code = 'package utils\n\nimport "fmt"\n\nfunc main() { fmt.Println("rewritten") }\n'
    result = await runner.execute(BY_ID["go"], code, stdin="", timeout_s=10)
    assert result.ok, result
    assert result.stdout == "rewritten\n"


async def test_bom_and_crlf_are_normalised(runner: DockerRunner) -> None:
    java = (
        "\ufeffpublic class Main {\r\n"
        "  public static void main(String[] a) { System.out.println(1); }\r\n"
        "}\r\n"
    )
    result = await runner.execute(BY_ID["java"], java, stdin="", timeout_s=10)
    assert result.ok, result
    assert result.stdout == "1\n"
    script = "echo one\r\necho two\r\n"
    result = await runner.execute(BY_ID["bash"], script, stdin="", timeout_s=10)
    assert result.ok, result
    assert result.stdout == "one\ntwo\n"


async def test_runtime_exception(runner: DockerRunner) -> None:
    result = await runner.execute(
        BY_ID["javascript"], "throw new Error('kaboom')", stdin="", timeout_s=10
    )
    assert result.phase == "run"
    assert result.exit_code == 1
    assert "kaboom" in result.stderr


async def test_exit_code_is_preserved(runner: DockerRunner) -> None:
    result = await runner.execute(BY_ID["python"], "raise SystemExit(42)", stdin="", timeout_s=10)
    assert result.exit_code == 42
    # A program exiting with the supervisor's own timeout code is still not a timeout.
    result = await runner.execute(BY_ID["bash"], "exit 124", stdin="", timeout_s=10)
    assert result.exit_code == 124
    assert not result.timed_out


async def test_timeout(runner: DockerRunner) -> None:
    started = time.monotonic()
    result = await runner.execute(
        BY_ID["python"], "print('tick', flush=True)\nwhile True: pass", stdin="", timeout_s=1
    )
    elapsed = time.monotonic() - started
    assert result.timed_out, result
    assert result.exit_code == KILLED_EXIT_CODE
    assert result.stdout == "tick\n"
    assert elapsed < 6, elapsed


async def test_background_child_does_not_delay_return(runner: DockerRunner) -> None:
    code = 'import subprocess\nsubprocess.Popen(["sleep", "300"])\nprint("done")\n'
    started = time.monotonic()
    result = await runner.execute(BY_ID["python"], code, stdin="", timeout_s=10)
    elapsed = time.monotonic() - started
    assert result.ok, result
    assert result.stdout == "done\n"
    assert not result.timed_out
    assert elapsed < 3, elapsed


async def test_memory_bomb_is_killed(runner: DockerRunner) -> None:
    code = "x = bytearray(1500 * 1024 * 1024)\nprint(len(x))"
    result = await runner.execute(BY_ID["python"], code, stdin="", timeout_s=10)
    assert result.exit_code != 0
    assert not result.timed_out
    assert "memory" in result.stderr.lower()


async def test_fork_bomb_is_contained(runner: DockerRunner) -> None:
    code = """
import os, sys
n = 0
while True:
    try:
        os.fork()
        n += 1
    except OSError as e:
        print("fork failed after", n, file=sys.stderr, flush=True)
        sys.exit(3)
"""
    started = time.monotonic()
    result = await runner.execute(BY_ID["python"], code, stdin="", timeout_s=2)
    elapsed = time.monotonic() - started
    assert elapsed < 15, elapsed
    assert result.exit_code != 0
    # The service must be fully usable afterwards.
    follow_up = await runner.execute(BY_ID["python"], "print('ok')", stdin="", timeout_s=5)
    assert follow_up.stdout == "ok\n"


async def test_network_is_disabled(runner: DockerRunner) -> None:
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 80), timeout=2); print('connected')\n"
        "except OSError as e:\n"
        "    print('blocked:', type(e).__name__)\n"
    )
    result = await runner.execute(BY_ID["python"], code, stdin="", timeout_s=10)
    assert result.stdout.startswith("blocked:"), result


async def test_filesystem_is_locked_down(runner: DockerRunner) -> None:
    code = """
import os
print("uid", os.getuid())
open("/work/scratch.txt", "w").write("ok"); print("work writable")
try:
    open("/usr/pwned", "w"); print("ROOTFS WRITABLE")
except OSError as e:
    print("rootfs read-only")
try:
    open("/etc/shadow").read(); print("shadow readable")
except OSError:
    print("shadow protected")
"""
    result = await runner.execute(BY_ID["python"], code, stdin="", timeout_s=10)
    assert result.stdout.splitlines() == [
        "uid 1000",
        "work writable",
        "rootfs read-only",
        "shadow protected",
    ], result


async def test_no_capabilities(runner: DockerRunner) -> None:
    result = await runner.execute(
        BY_ID["python"],
        "print(open('/proc/self/status').read().split('CapEff:')[1].split()[0])",
        stdin="",
        timeout_s=10,
    )
    assert result.stdout.strip() == "0000000000000000"


async def test_output_cap_and_flood_protection(runner: DockerRunner) -> None:
    settings = make_settings(runner="docker", sandbox_pool_size=0, max_output_bytes=2048)
    small = DockerRunner(settings)
    await small.start()
    try:
        result = await small.execute(BY_ID["python"], "print('y' * 3000)", stdin="", timeout_s=10)
        assert result.truncated
        assert len(result.stdout.encode()) == 2048
        assert result.exit_code == 0

        flood = "import sys\nwhile True: sys.stdout.write('z' * 65536)"
        started = time.monotonic()
        result = await small.execute(BY_ID["python"], flood, stdin="", timeout_s=5)
        elapsed = time.monotonic() - started
        # A flood is contained one of two ways, both correct: the inline reader trips the
        # 4x-cap abort and kills the container, or (if a loaded daemon streams/kills too
        # slowly) the async backstop kills it. Assert the invariants that hold either way:
        # the slot is not wedged, the program is killed, and API memory never exceeds the
        # cap. (Which path wins depends on daemon timing, so don't pin it -- see the
        # history of this test.)
        assert elapsed < 5 + BACKSTOP_GRACE_S + 8, elapsed
        assert result.exit_code == KILLED_EXIT_CODE
        assert len(result.stdout.encode()) <= 2048
        assert result.truncated or "hard time limit" in result.stderr
    finally:
        await small.stop()


async def test_concurrency_and_capacity(runner: DockerRunner) -> None:
    code = "import time; time.sleep(1.5); print('done')"
    tasks = [
        asyncio.create_task(runner.execute(BY_ID["python"], code, stdin="", timeout_s=10))
        for _ in range(5)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ok = [r for r in results if not isinstance(r, BaseException)]
    rejected = [r for r in results if isinstance(r, NoCapacityError)]
    assert len(ok) == 3, results
    assert len(rejected) == 2, results
    assert all(r.stdout == "done\n" for r in ok)


async def test_go_cache_trim_file_is_writable(runner: DockerRunner) -> None:
    """Go aborts builds when it cannot rewrite GOCACHE/trim.txt (once per day).

    The image links it into /tmp; if this ever regresses Go breaks 24 h after a build
    even though every other test passes right after building.
    """
    result = await runner.execute(
        BY_ID["bash"],
        'readlink /opt/gocache/trim.txt; touch "$(readlink /opt/gocache/trim.txt)" && echo ok',
        stdin="",
        timeout_s=10,
    )
    assert result.stdout == "/tmp/glimpse-gocache-trim.txt\nok\n", result


async def test_health_and_versions(runner: DockerRunner) -> None:
    health = await runner.health()
    assert health["pool_size"] == 1
    assert health["limits"]["network"] == "none"
    versions = await runner.versions()
    assert set(versions) == set(BY_ID)
    assert versions["python"].startswith("Python 3.12")
    assert "go1." in versions["go"]
    assert versions["rust"].startswith("rustc 1.")


async def test_no_leaked_containers_after_stop() -> None:
    settings = make_settings(runner="docker", sandbox_pool_size=2)
    fresh = DockerRunner(settings)
    await fresh.start()
    await asyncio.sleep(3)  # let the pool warm up
    assert len(_sandbox_containers()) >= 1
    await fresh.execute(BY_ID["python"], "print(1)", stdin="", timeout_s=5)
    await fresh.stop()
    assert _sandbox_containers() == []
