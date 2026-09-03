# Architecture

```
client / CLI / demo
        │  POST /v1/execute {language, code, stdin, timeout_s}
        ▼
┌────────────────────────────────────────────────────────────┐
│ FastAPI app  (glimpse/api)                                 │
│  request-id · body-size guard · CORS · API key · rate limit │
│  languages.resolve() · size limits · timeout clamp          │
└───────────────┬────────────────────────────────────────────┘
                │ runner.execute(language, code, stdin=, timeout_s=)
                ▼
      ┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
      │ DockerRunner    │    │ LambdaRunner     │    │ UnsafeLocalRunner│
      │ warm pool of    │    │ boto3 invoke →   │    │ subprocess on    │
      │ hardened        │    │ lambda_handler → │    │ the host         │
      │ containers      │    │ execute_local()  │    │ execute_local()  │
      └─────────────────┘    └──────────────────┘    └──────────────────┘
                │
                ▼
   ExecutionResult {language, phase, exit_code, timed_out, stdout, stderr, duration_ms, truncated}
```

## Modules

| Module | Responsibility |
|---|---|
| `glimpse/languages.py` | **The** language registry: ids, aliases, filename, compile/run argv templates, env, compile timeout. Every backend renders its commands from it. |
| `glimpse/execution.py` | `execute_local()`: fresh temp dir, minimal env, compile → run, process-group SIGKILL on timeout, byte-capped output, cleanup. Standard library only, so the Lambda image needs no third-party packages. |
| `glimpse/runners/base.py` | The `Runner` interface (`start / stop / execute / health / versions`) and `create_runner(settings)`. |
| `glimpse/runners/docker.py` | The reference sandbox (below). |
| `glimpse/runners/lambda_.py` | Thin, non-blocking wrapper around `boto3` `invoke` with retries disabled. |
| `glimpse/runners/local.py` | Host subprocess; tests and explicit opt-in only. |
| `glimpse/api/` | App factory, routes, structured errors, API keys, sliding-window rate limiter. |
| `glimpse/models.py` | pydantic schemas for the public API. |
| `glimpse/config.py` | `Settings` (`GLIMPSE_*` env vars / `.env`). |
| `glimpse/client.py`, `glimpse/cli.py` | Python client (sync + async) and the `glimpse` CLI. |
| `lambda_handler.py` | Lambda entry point: event → `execute_local` → dict. |

Program failures are **data**: compile errors, crashes, timeouts and kills are all
`ExecutionResult`s. Only failures of the service raise (`RunnerError`, `NoCapacityError`),
and the API maps those to `500` / `503`.

## The Docker runner

Lifecycle:

1. `start()` connects to the daemon, verifies the sandbox image exists, removes any container
   labelled `glimpse.sandbox=1` left over from a previous process, and starts a background task
   that keeps `GLIMPSE_SANDBOX_POOL_SIZE` warm containers in an `asyncio.Queue`.
2. `execute()`:
   - rejects immediately with `NoCapacityError` (→ `503` + `Retry-After`) if
     `GLIMPSE_SANDBOX_MAX_CONCURRENCY` executions are already in flight;
   - takes a warm container from the pool (or creates one on demand);
   - on a worker thread: runs `glimpse.source.prepare()` (BOM/CRLF, Java package strip +
     class name, Go package), writes the file and `stdin` into the container's `/work`
     tmpfs, runs the
     compile step (if any) and then the program, each as
     `glimpse-run -t <seconds> [-i /work/stdin] -- <argv...>`, streaming demultiplexed
     stdout/stderr with a byte cap and reading the exit code from `exec_inspect`;
   - **always** kills and removes the container afterwards and wakes the refill task.
3. `stop()` cancels the refill task, removes pooled containers and sweeps the label again.

`glimpse-run` (`sandbox/glimpse-run/main.go`, ~80 lines, built into the sandbox image) is
the in-container supervisor: it starts the program in its own process group with stdin
redirected from a file, SIGKILLs the group at the deadline (exit 124), and SIGKILLs the
group again the moment the main process exits so background children cannot keep the
exec's stdout/stderr open — the API returns as soon as the program does. A process that
moves itself into a new session (`setsid`) escapes the group kill; the watchdog thread
covers that by killing the container 2 s after the deadline, and an `asyncio.wait_for`
backstop wraps the whole worker-thread call. Exit 124 at or after the deadline — and any
watchdog kill — is reported as `timed_out` (with the documented `exit_code` 137); any
other 137 is the OOM killer or the pids limit.

Every docker-py call runs via `asyncio.to_thread`, so the event loop never blocks.

Why no `put_archive`? Docker refuses `PUT /containers/{id}/archive` for containers with a
read-only rootfs, even into a tmpfs. Files are therefore written by a short `sh` exec that
base64-decodes environment variables with the shell's builtin `printf` (chunked under the
kernel's 128 KiB per-string limit). This keeps the rootfs read-only and avoids any host path,
so the API can itself run in a container with only the Docker socket mounted.

Go under a read-only rootfs: Go ≥ 1.20 compiles the standard library on demand into
`GOCACHE`. The sandbox image pre-warms a cache for common packages at build time; Go only
needs read access for cache hits and puts the user's package output in `/tmp`. One wrinkle:
once a day Go "trims" the cache and aborts if it cannot rewrite `GOCACHE/trim.txt`, so the
image links that file into `/tmp` (a regression test checks it — this only shows up 24 h
after an image build).

Measured on an M-series laptop (Docker Desktop, warm pool): Python/JS/C ≈ 0.2 s end to end,
Go ≈ 0.4 s, C++ ≈ 0.6 s, Java ≈ 0.9 s, Kotlin ≈ 4.3 s (kotlinc start-up).

## The Lambda runner

`lambda_handler.handler` accepts the same fields as `/v1/execute` and returns the
`ExecutionResult` dict; `{"action": "versions"}` reports toolchain versions. Each invocation
uses its own `mkdtemp` under `/tmp` which is removed afterwards (earlier versions wrote fixed
paths that leaked between warm invocations). `LambdaRunner` validates the payload and maps
`FunctionError` to `RunnerError`.

## Adding a language

1. Add a `Language` to `LANGUAGES` in `glimpse/languages.py`: id, fence-style aliases,
   filename, compile/run argv templates (`{src}`, `{out}`, `{work}`, `{tmp}`, `{stem}`), a
   `version` argv, any env, and a `sample` that reads one line from stdin and prints
   `hello, <name>` first.
2. Install the toolchain in `sandbox/Dockerfile` **and** `lambda/Dockerfile`.
3. Add a tab to the demo's `src/lib/languages.ts` (editor mode + samples).

That is all: `tests/test_languages.py` enforces the registry invariants, the Docker
integration tests and `lambda/smoke_test.py` run every registry sample end-to-end, and
`GET /v1/languages` exposes the new entry. Language-specific source fixes (Java's package
declaration and class name, Go's package clause) live in `glimpse/source.py`.
