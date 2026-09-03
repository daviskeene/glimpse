# Glimpse

[![CI](https://github.com/daviskeene/glimpse/actions/workflows/ci.yml/badge.svg)](https://github.com/daviskeene/glimpse/actions/workflows/ci.yml)

Glimpse is a self-hosted HTTP API that runs untrusted code snippets in isolated sandboxes:
code in, result out. It is built for web products that need to execute a snippet cheaply —
for example a chat UI that renders an AI-generated code block with a play button.

- **10 languages**: Python, JavaScript, TypeScript, Bash, C, C++, Rust, Go, Java, Kotlin.
- **One fresh, locked-down container per run** (no network, read-only rootfs, memory / CPU /
  pid limits, non-root, all capabilities dropped) — destroyed afterwards, never reused.
- **A stable `/v1` API** where program failures are results and only service failures are errors.
- **Made for LLM output**: Markdown-fence aliases (`sh`, `ts`, `c++`, …), Java files named after
  the public class, Go's package clause fixed, BOM/CRLF normalised, compiler warnings returned.
- **Python client + `glimpse` CLI**, a `docker compose` one-liner, and an AWS Lambda backend
  for serverless deployments.

Live demo: **[glimpse.daviskeene.com](https://glimpse.daviskeene.com)**

## Quickstart

```sh
git clone https://github.com/daviskeene/glimpse && cd glimpse
docker compose up            # builds the sandbox image, starts the API on :8000
```

```sh
curl -s localhost:8000/v1/execute \
  -H 'content-type: application/json' \
  -d '{"language": "python", "code": "print(input()[::-1])", "stdin": "glimpse"}'
```

```json
{"language":"python","phase":"run","exit_code":0,"timed_out":false,
 "stdout":"espmilg\n","stderr":"","duration_ms":38,"truncated":false,"compile_stderr":""}
```

Interactive OpenAPI docs are at `http://localhost:8000/docs`.

### Without compose (development)

```sh
uv sync                      # Python >= 3.11; https://docs.astral.sh/uv/
make sandbox                 # docker build -t glimpse-sandbox sandbox/
uv run glimpse serve         # http://127.0.0.1:8000
```

## API

Full reference: [docs/api.md](docs/api.md) (or `/docs` on a running server).

### `POST /v1/execute`

| Field       | Type   | Notes                                                                 |
|-------------|--------|-----------------------------------------------------------------------|
| `language`  | string | id or Markdown-fence alias: `python`/`py`, `javascript`/`js`, `typescript`/`ts`, `bash`/`sh`, `c`, `cpp`/`c++`, `rust`/`rs`, `go`, `java`, `kotlin`/`kt` |
| `code`      | string | ≤ 64 KiB. BOM/CRLF are normalised; Java files are named after the public class; Go's package clause is rewritten to `main`. |
| `stdin`     | string | optional, ≤ 64 KiB                                                    |
| `timeout_s` | number | optional, 1–30, wall-clock limit for the run phase (default 10)       |

Response (`200`):

| Field         | Meaning                                                                         |
|---------------|---------------------------------------------------------------------------------|
| `phase`       | `compile` if the compiler failed, otherwise `run`                                |
| `exit_code`   | exit status of that phase; `137` means killed (timeout, memory or process limit) |
| `timed_out`   | `true` if the phase hit its time limit                                           |
| `stdout`, `stderr` | UTF-8 text, each capped at 64 KiB                                           |
| `truncated`   | `true` if either stream was cut at the cap                                       |
| `compile_stderr` | compiler warnings when compilation succeeded                                  |
| `duration_ms` | wall-clock time of that phase                                                    |

**Program failures are `200`s.** A compile error, an uncaught exception, a non-zero exit or a
timeout all come back as a normal result — look at `phase`, `exit_code` and `timed_out`.
Only failures *of the service* use error status codes, always shaped as
`{"error": {"code": "...", "message": "..."}}`:

| Status | `code`                              | When                                            |
|--------|-------------------------------------|-------------------------------------------------|
| 400    | `unsupported_language`              | unknown language id/alias (message lists them)   |
| 401    | `unauthorized`                      | API keys are configured and none/invalid given   |
| 413    | `code_too_large`, `stdin_too_large`, `payload_too_large` | size limits                 |
| 422    | `validation_error`                  | malformed request (`details` lists the fields)   |
| 429    | `rate_limited`                      | per-client limit hit; honour `Retry-After`       |
| 503    | `no_capacity`                       | all sandboxes busy; honour `Retry-After`         |
| 500    | `runner_error`                      | the backend failed                               |

### Other endpoints

- `GET /v1/languages` — ids, aliases, file names, sample programs and toolchain versions.
- `GET /health` — backend status (pool size, in-flight executions, limits).

## CLI and Python client

```sh
uv run glimpse run hello.go                      # language inferred from the extension
uv run glimpse run --lang py - < script.py       # source from stdin
uv run glimpse run main.c --stdin-file input.txt --timeout 5
uv run glimpse languages
```

The process exit code mirrors the program's (`124` on timeout), stdout/stderr are passed
through, and a one-line status goes to stderr. `GLIMPSE_URL` / `GLIMPSE_API_KEY` (or
`--url` / `--api-key`) select the server.

```python
from glimpse.client import GlimpseClient

with GlimpseClient("http://localhost:8000") as client:
    result = client.execute("go", 'package main\nimport "fmt"\nfunc main(){ fmt.Println("hi") }')
    print(result.stdout, result.exit_code, result.duration_ms)
```

`AsyncGlimpseClient` has the same methods as coroutines. API errors raise `GlimpseAPIError`
with `.status_code`, `.code` and `.retry_after`.

## Backends

Set `GLIMPSE_RUNNER` to choose how code is executed. Both real backends share the same language
registry and return the same result shape.

| Runner         | Where code runs                                   | Isolation                                                                    | Use it for                       |
|----------------|---------------------------------------------------|------------------------------------------------------------------------------|----------------------------------|
| `docker`       | a fresh `glimpse-sandbox` container per request   | no network, read-only rootfs + capped tmpfs, 512 MiB / 1 CPU / 128 pids, `cap_drop ALL`, `no-new-privileges`, non-root, `glimpse-run` supervisor with hard kills | local and self-hosted deployments |
| `lambda`       | an AWS Lambda micro-VM (`lambda/Dockerfile`)      | Firecracker VM per function instance; no network if the function has none; per-invocation temp dir; hard kill on timeout | serverless / the public demo     |
| `unsafe-local` | a subprocess **on the API host**                  | **none** — only for tests and trusted single-user use                        | CI, hacking on the API           |

The Docker runner is the reference implementation: [docs/security.md](docs/security.md) lists
every control and, just as importantly, what is *not* covered.

## Configuration

Everything is a `GLIMPSE_*` environment variable (or a `.env` file — see
[`.env.example`](.env.example)). The ones you are most likely to touch:

| Variable                          | Default          | Purpose                                        |
|-----------------------------------|------------------|------------------------------------------------|
| `GLIMPSE_RUNNER`                  | `docker`         | `docker` \| `lambda` \| `unsafe-local`         |
| `GLIMPSE_API_KEYS`                | *(empty = open)* | comma-separated bearer keys for `/v1/execute`  |
| `GLIMPSE_RATE_LIMIT`              | `30/minute`      | per client IP; `off` to disable                |
| `GLIMPSE_GLOBAL_RATE_LIMIT`       | *(off)*          | across all clients — set it on a public instance |
| `GLIMPSE_TRUST_PROXY` / `CLIENT_IP_HEADER` | `false` / — | behind a proxy: rate-limit on the real client IP |
| `GLIMPSE_CORS_ORIGINS`            | `*`              | comma-separated origins                        |
| `GLIMPSE_DEFAULT_TIMEOUT_S` / `MAX_TIMEOUT_S` | `10` / `30` | run-phase limits                       |
| `GLIMPSE_SANDBOX_POOL_SIZE`       | `2`              | warm containers kept ready                     |
| `GLIMPSE_SANDBOX_MAX_CONCURRENCY` | `4`              | in-flight executions before `503`              |
| `GLIMPSE_SANDBOX_MEMORY_MB` / `CPUS` / `PIDS_LIMIT` | `512` / `1.0` / `128` | per-sandbox limits    |
| `GLIMPSE_LAMBDA_FUNCTION_NAME`    | —                | required for the `lambda` runner               |

## Development

```sh
make sandbox        # build the sandbox image
make test           # unit tests (no Docker needed)
make test-docker    # integration tests: every language, timeouts, OOM, fork bomb, network, fs
make lambda-smoke   # every language through the Lambda image (after make lambda-local)
make lint           # ruff + mypy
make dev            # API with auto-reload
make up             # docker compose up --build
```

```
glimpse/            the package
  languages.py      the single language registry: commands, aliases, samples (tests and the
                    Lambda smoke test iterate it; add a language here + in the Dockerfiles)
  source.py         BOM/CRLF normalisation, Java class-name and Go package fixes
  execution.py      subprocess core shared by the Lambda handler and the unsafe-local runner
  runners/          docker.py · lambda_.py · local.py behind one Runner interface
  api/              FastAPI app: routes, error shapes, API keys, rate limiting
  client.py, cli.py
sandbox/            the sandbox image (toolchains only, no app code) + glimpse-run supervisor
lambda/             the Lambda image; lambda_handler.py is the entry point
demo/               the web playground (Vite + React)
docs/               architecture · security · deploy · api
```

Adding a language is one `Language` entry in `glimpse/languages.py` plus the toolchain in the
two Dockerfiles — see [docs/architecture.md](docs/architecture.md#adding-a-language).

## Deploying

The public instance is one small VM: `make prod` brings up the API, the sandbox image and
Caddy (TLS) behind Cloudflare's free tier. [docs/deploy.md](docs/deploy.md) has the full
recipe, plus the Lambda image (build → ECR → function) for serverless deployments.

## License

MIT — see [LICENSE](LICENSE).
