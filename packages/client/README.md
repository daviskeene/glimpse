# @glimpse-run/client

Typed, zero-dependency client for the [Glimpse](https://github.com/daviskeene/glimpse) code
execution API. Runs anywhere `fetch` does: browsers, Node 18+, Bun, Deno, Cloudflare Workers,
Vercel Edge.

```sh
npm install @glimpse-run/client
```

```ts
import { createClient, isSuccess } from "@glimpse-run/client";

const glimpse = createClient({ baseUrl: "https://api.glimpse.daviskeene.com" });

const run = await glimpse.execute({ language: "py", code: "print(input()[::-1])", stdin: "glimpse" });
run.stdout;            // "espmilg\n"
run.exit_code;         // 0
isSuccess(run);        // true
run.meta.timing;       // { queue: 0, acquire: 1, upload: 98, run: 140, total: 281 } (ms, server-side)
run.meta.roundTripMs;  // as seen by this client
```

## What you get back

`execute()` resolves for **every program outcome**. A compile error, an uncaught exception,
a non-zero exit or a timeout is a normal result; look at `phase`, `exit_code` and `timed_out`.
The wire fields are spread unchanged (`language`, `phase`, `exit_code`, `timed_out`, `stdout`,
`stderr`, `duration_ms`, `truncated`, `compile_stderr`) and `meta` adds what the client learned
from the response: `requestId`, the parsed `Server-Timing` phases, and `roundTripMs`.

It rejects only when the **service** fails:

| Error | When |
|---|---|
| `GlimpseApiError` | non-2xx response; `status`, `code` (`rate_limited`, `no_capacity`, `unsupported_language`, `code_too_large`, `unauthorized`, ...), `retryAfter`, `requestId`, `details` |
| `GlimpseNetworkError` | the request never got a response (offline, DNS, CORS, connection refused) |
| `GlimpseTimeoutError` | your `timeoutMs` elapsed |
| `AbortError` | you aborted the `signal` |

## Options

```ts
createClient({
  baseUrl: "http://localhost:8000", // default
  apiKey: "...",                     // Authorization: Bearer, if the server requires keys
  headers: { "x-app": "docs" },      // sent with every request
  fetch: customFetch,                // polyfill or test double
  retry: { maxAttempts: 3, maxDelayMs: 10_000 }, // 429/503 only, honours Retry-After; default: no retries
});

await glimpse.execute(input, {
  signal,          // AbortSignal
  timeoutMs: 15_000,
  requestId: "my-trace-id", // echoed back as X-Request-ID
  retry: { maxAttempts: 1 },
});

await glimpse.languages(); // ids, aliases, toolchain versions, samples
await glimpse.health();    // runner, warm pool, limits (throws GlimpseApiError 503 when unhealthy)
```

## In the browser

A public site cannot hide an API key. Public Glimpse instances rely on CORS plus rate and
concurrency limits instead, so leave `apiKey` unset there. Bodies are sent as strings so the
browser sets `Content-Length` (the API refuses chunked POSTs).

## Related

- `@glimpse-run/react`: `GlimpseProvider`, `useRun`, `useLanguages`, `useHealth`.
- Python: `from glimpse.client import GlimpseClient` in the main repository.
