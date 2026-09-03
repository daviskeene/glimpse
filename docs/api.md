# API reference (`/v1`)

Base URL: your server, e.g. `http://localhost:8000`. All requests and responses are JSON.
A live OpenAPI UI is served at `/docs` and the schema at `/openapi.json`.

## Authentication

Open by default. If the server sets `GLIMPSE_API_KEYS`, `POST /v1/execute` requires

```
Authorization: Bearer <key>
```

and answers `401 unauthorized` (with `WWW-Authenticate: Bearer`) otherwise. `GET` endpoints
never require a key.

## Errors

Every non-2xx response has the shape

```json
{"error": {"code": "rate_limited", "message": "rate limit exceeded (30/minute); retry in 12s", "details": null}}
```

| Status | `code` | Notes |
|---|---|---|
| 400 | `unsupported_language` | the message lists supported ids and aliases |
| 401 | `unauthorized` | see Authentication |
| 404 | `not_found` | |
| 411 | `length_required` | `POST` without a `Content-Length` header (chunked bodies are not accepted) |
| 413 | `code_too_large` / `stdin_too_large` / `payload_too_large` | limits are configurable server-side (default 64 KiB each) |
| 422 | `validation_error` | `details` is a list of `{loc, msg, type}` |
| 429 | `rate_limited` | per-client or (message says so) global limit; `Retry-After` header in seconds |
| 500 | `runner_error` / `internal_error` | |
| 503 | `no_capacity` / `unhealthy` | `Retry-After: 1` — all sandboxes busy, try again |

API responses carry an `X-Request-ID` header (yours is echoed if you send one; CORS
preflights and last-resort 500s may lack it).

## `POST /v1/execute`

Compile (if needed) and run a snippet.

Request body:

| Field | Type | Required | Constraints |
|---|---|---|---|
| `language` | string | yes | id or alias, case-insensitive (see `GET /v1/languages`) |
| `code` | string | yes | non-empty, ≤ `GLIMPSE_MAX_CODE_BYTES` (64 KiB) |
| `stdin` | string | no | ≤ `GLIMPSE_MAX_STDIN_BYTES` (64 KiB); made available on standard input |
| `timeout_s` | number | no | ≥ 1; clamped to the server's `GLIMPSE_MAX_TIMEOUT_S` (default 30); default `GLIMPSE_DEFAULT_TIMEOUT_S` (10) |

Unknown fields are rejected (`422`).

Response `200`:

| Field | Type | Meaning |
|---|---|---|
| `language` | string | canonical id (`"py"` → `"python"`) |
| `phase` | `"compile"` \| `"run"` | the last phase that ran. `compile` only appears when the compiler failed or timed out |
| `exit_code` | integer | exit status of that phase. `137` = killed by SIGKILL: timeout, memory limit or process limit (stderr says which is likely) |
| `timed_out` | boolean | the phase hit its limit (`timeout_s` for run; per-language for compile: 20–60 s) |
| `stdout` | string | UTF-8 (invalid bytes replaced), ≤ `GLIMPSE_MAX_OUTPUT_BYTES` (64 KiB) |
| `stderr` | string | same cap; may end with a `[glimpse] ...` note explaining a kill |
| `duration_ms` | integer | wall-clock time of that phase |
| `truncated` | boolean | stdout or stderr was cut at the cap. A program that floods far beyond it (4x) is killed with `exit_code` 137, on every backend |
| `compile_stderr` | string | compiler diagnostics (warnings) when compilation **succeeded**; empty for interpreted languages and on compile failure (then `stderr` holds the compiler output) |

Examples:

```sh
# stdin round-trip
curl -s localhost:8000/v1/execute -H 'content-type: application/json' \
  -d '{"language":"python","code":"print(input()[::-1])","stdin":"glimpse"}'
# {"language":"python","phase":"run","exit_code":0,"timed_out":false,"stdout":"espmilg\n","stderr":"","duration_ms":38,"truncated":false,"compile_stderr":""}

# compile error → still 200
curl -s localhost:8000/v1/execute -H 'content-type: application/json' \
  -d '{"language":"c","code":"int main( {"}'
# {"language":"c","phase":"compile","exit_code":1,"timed_out":false,"stdout":"","stderr":"/work/main.c:1:10: error: ...","duration_ms":21,"truncated":false}

# timeout
curl -s localhost:8000/v1/execute -H 'content-type: application/json' \
  -d '{"language":"javascript","code":"for(;;){}","timeout_s":2}'
# {"language":"javascript","phase":"run","exit_code":137,"timed_out":true,"stdout":"","stderr":"","duration_ms":2003,"truncated":false}
```

Before the file is written the source is normalised: a leading byte-order mark is
removed, `\r\n` / `\r` line endings become `\n`, and a trailing newline is added.

Language notes:

- **Java**: a `package` declaration is removed (snippets run as a single file), and the
  file is named after the first `public class` / `interface` / `enum` / `record`
  (`public class Solution` → `Solution.java`, run as `Solution`); with no public type it
  is `Main.java`.
- **Kotlin**: top-level `fun main()`; compiling takes a few seconds.
- **Go**: a single file; a `package` clause other than `main` is rewritten to `package main`.
  Standard library only (no module downloads — there is no network).
- **Rust**: `rustc -O --edition 2021`, single file, standard library only.
- **TypeScript**: run directly by Node's built-in type stripping (no `tsc`, no type checking;
  type-only syntax is erased).
- **Bash**: `bash main.sh`; `sh`, `shell` and `zsh` fences map here.
- **Python**: `numpy`, `pandas`, `requests`, `beautifulsoup4`, `python-dateutil`, `pytz` are installed (network calls will fail).
- **C / C++**: `gcc -std=gnu17 -lm` / `g++ -std=gnu++20`, `-O2 -Wall` (warnings land in `compile_stderr`).

## `GET /v1/languages`

```json
[
  {"id": "python", "name": "Python", "aliases": ["py", "python3", "py3"], "version": "Python 3.12.11",
   "compiled": false, "filename": "main.py", "sample": "import sys, platform\n..."},
  {"id": "go", "name": "Go", "aliases": ["golang"], "version": "go version go1.25.3 linux/arm64",
   "compiled": true, "filename": "main.go", "sample": "package main\n..."}
]
```

Ids: `python`, `javascript`, `typescript`, `bash`, `c`, `cpp`, `rust`, `go`, `java`, `kotlin`.
Aliases follow Markdown fence tags (`py`, `js`, `node`, `ts`, `sh`, `shell`, `zsh`, `c++`,
`rs`, `golang`, `kt`, …). `filename` is the file the code is written to; `sample` is a small
program that reads one line from stdin. `version` is `null` if the backend cannot probe it.

## `GET /health`

```json
{"status": "ok", "runner": "docker", "version": "1.0.0",
 "details": {"image": "glimpse-sandbox", "pool_ready": 2, "pool_size": 2, "in_flight": 0,
             "max_concurrency": 4, "limits": {"memory_mb": 512, "cpus": 1.0, "pids": 128, "tmpfs_mb": 64, "network": "none"}}}
```

`503 unhealthy` if the backend is unreachable.

## `GET /`

Service name, version, runner and endpoint list.
