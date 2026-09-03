# Security model

Glimpse executes code you do not trust. This page states exactly what each backend
enforces, how, and what it does **not** cover, so you can decide where it is appropriate
to run it.

## Threat model

The attacker controls `code` and `stdin` and wants to: read or tamper with another
request's data, reach the network, exhaust CPU / memory / disk / pids, persist across
requests, or escape to the API host. Glimpse's job is to make every request a
short-lived, resource-capped, single-tenant box and to fail closed when limits are hit.

## Docker runner (reference backend)

One container per execution, created from `sandbox/Dockerfile` with these host-config
settings (`glimpse/runners/docker.py::_create_container`):

| Control | Setting | Why |
|---|---|---|
| Fresh container per run | create → run → `remove(force=True, v=True)` | nothing (files, processes, caches) survives between two requests |
| Network | `network_mode=none`, `network_disabled=True` | no egress, no DNS, no reaching the API or the daemon |
| Root filesystem | `read_only=True` | toolchains and system files cannot be modified |
| Writable space | tmpfs `/work` and `/tmp`, `size=64m`, `nosuid,nodev` (`exec` allowed: compiled binaries run from `/work`) | bounded disk, no persistent state, nothing touches the host fs |
| Memory | `mem_limit` = `memswap_limit` = 512 MiB | OOM-kill instead of swapping the host |
| CPU | `nano_cpus` (1.0 CPU) | a spinning loop cannot starve other sandboxes |
| Processes | `pids_limit=128` | fork bombs hit the limit inside the sandbox |
| Capabilities | `cap_drop=["ALL"]` (`CapEff` is `0`) | no mounts, no raw sockets, no ptrace, no chown tricks |
| Privilege escalation | `security_opt=["no-new-privileges:true"]` | setuid binaries cannot elevate |
| User | `user=sandbox` (uid 1000), `HOME=/work` | not root inside the container |
| Init | `init=True` (tini) | zombies and orphans are reaped |
| ulimits | `nofile=1024`, `core=0`, `fsize` = tmpfs size | no core dumps, no fd exhaustion, no giant files |
| Time | `glimpse-run` supervisor: SIGKILL of the program's process group at the deadline **and** when the main process exits (no lingering children) + watchdog kill 2 s later + async backstop | a wedged process, or one that leaves daemons behind, can never hold a slot |
| Output | 64 KiB per stream, hard kill after 4× that | a flood cannot exhaust API memory or the daemon |
| Input | 64 KiB code, 64 KiB stdin, 1–30 s timeout | bounded work per request |
| Concurrency | `sandbox_max_concurrency`, `503 + Retry-After` beyond it | back-pressure instead of queueing forever |
| Seccomp / AppArmor | Docker defaults | the default seccomp profile blocks ~40 syscalls; a custom profile is not applied |
| Image contents | toolchains only; no app code, config or secrets; built from `sandbox/` with its own context | there is nothing worth exfiltrating inside |
| Leak sweeping | containers labelled `glimpse.sandbox=1`; swept on start/stop | a crashed API cannot leave sandboxes running |

`tests/test_docker.py` exercises each of these (memory bomb, fork bomb, network,
filesystem, capabilities, timeouts, output floods, concurrency, leak check).

### What the Docker runner does *not* protect against

- **Kernel exploits.** Containers share the host kernel. A container escape via a kernel
  bug is out of scope; use gVisor / Kata / Firecracker (or the Lambda backend) if your
  threat model includes it.
- **The Docker socket.** With `GLIMPSE_RUNNER=docker` the API process talks to the daemon,
  which is root-equivalent on the host. Anyone who can execute code *in the API process*
  (not in a sandbox) owns the host. Keep the API image minimal and do not expose the socket
  further.
- **Side channels** (timing, CPU cache) between concurrently running sandboxes.
- **Denial of wallet.** Rate limiting is per API process and per client IP; in a
  multi-replica deployment put a real limiter in front, and require API keys
  (`GLIMPSE_API_KEYS`) for anything but a public demo.
- **Toolchain bugs.** Compilers run as the sandbox user with the same limits as user code,
  but a compiler is a large attack surface.

## Lambda runner

The Lambda micro-VM (Firecracker) is the isolation boundary, which is stronger than a
container against kernel exploits. Inside it:

- each invocation gets a fresh `mkdtemp` under `/tmp` that is removed afterwards;
- compile and run each have a hard `SIGKILL` timeout applied to the whole process group;
- output is capped; the environment is reduced to `PATH`, locale and toolchain variables
  (no AWS credentials reach user code).

Caveats: a *warm* Lambda instance is reused for the next invocation, so `/tmp` and process
state persist between requests **in the same instance**; Glimpse mitigates this by using a
per-invocation directory and by killing the process group, but a determined program could
still leave something in `/tmp`. Network access is whatever the function's configuration
allows — attach it to a VPC without egress if you need the "no network" guarantee. Memory
and CPU are set on the function (2048 MB is a comfortable default; Kotlin needs ≥ 1024 MB).

## `unsafe-local` runner

No isolation at all: code runs as the API's user on the API's machine, with only the
timeout and output caps. It exists so the test suite and quick experiments do not need
Docker. Never expose it.

## Deployment recommendations

- Run the API behind TLS and set `GLIMPSE_API_KEYS` unless it is intentionally public.
- Set `GLIMPSE_CORS_ORIGINS` to your front-end origin instead of `*`.
- Put the API on a dedicated host/VM; do not co-locate it with anything sensitive when using
  the Docker runner.
- Keep the sandbox image rebuilt regularly to pick up toolchain and base-image fixes.

## Reporting

Please report security issues privately to the maintainer (see the GitHub profile) rather
than opening a public issue.
