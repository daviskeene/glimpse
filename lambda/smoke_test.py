"""Smoke-test a Glimpse Lambda image running under the Runtime Interface Emulator.

docker run -d --rm --name glimpse-lambda -p 9000:8080 glimpse-lambda
python lambda/smoke_test.py            # exits non-zero on any failure
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

URL = "http://localhost:9000/2015-03-31/functions/function/invocations"

# The registry is stdlib-only, so this script stays runnable with a bare python3.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from glimpse.languages import LANGUAGES  # noqa: E402


def invoke(event: dict[str, object]) -> dict[str, object]:
    req = urllib.request.Request(
        URL, data=json.dumps(event).encode(), headers={"content-type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310
        return json.load(resp)  # type: ignore[no-any-return]


def wait_ready(attempts: int = 60) -> None:
    for _ in range(attempts):
        try:
            if invoke({"action": "ping"}).get("ok"):
                return
        except OSError:
            pass
        time.sleep(1)
    sys.exit("lambda emulator did not become ready")


def main() -> int:
    wait_ready()
    print("versions:", json.dumps(invoke({"action": "versions"}).get("versions"), indent=1))
    failed = False
    for lang in LANGUAGES:
        started = time.time()
        result = invoke({"language": lang.id, "code": lang.sample, "stdin": "glimpse\n"})
        stdout = str(result.get("stdout", ""))
        good = stdout.startswith("hello, glimpse\n") and result.get("exit_code") == 0
        failed |= not good
        status = "PASS" if good else "FAIL"
        print(f"{lang.id:10s} {time.time() - started:5.1f}s {status} {json.dumps(result)[:200]}")
    timeout = invoke({"language": "python", "code": "while True: pass", "timeout_s": 1})
    good = timeout.get("timed_out") is True and timeout.get("exit_code") == 137
    failed |= not good
    print(f"{'timeout':10s}        {'PASS' if good else 'FAIL'} {json.dumps(timeout)[:200]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
