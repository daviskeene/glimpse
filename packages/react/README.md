# @glimpse-run/react

React hooks for the [Glimpse](https://github.com/daviskeene/glimpse) code execution API.
Unstyled: you bring the button and the output box, the hooks bring the state machine.

```sh
npm install @glimpse-run/react @glimpse-run/client
```

```tsx
import { GlimpseProvider, useRun, isSuccess } from "@glimpse-run/react";

function App() {
  return (
    <GlimpseProvider baseUrl="https://api.glimpse.daviskeene.com">
      <Snippet />
    </GlimpseProvider>
  );
}

function Snippet() {
  const { run, running, result, error } = useRun();
  return (
    <>
      <button onClick={() => run({ language: "py", code: "print(1 + 1)" })} disabled={running}>
        {running ? "Running…" : "Run"}
      </button>
      {result && <pre>{result.stdout || result.stderr}</pre>}
      {result && !isSuccess(result) && <span>exit {result.exit_code}</span>}
      {error && <span role="alert">{error.message}</span>}
    </>
  );
}
```

## Hooks

- **`useRun({ client?, requestOptions? })`** → `{ status, result, error, startedAt, finishedAt, running, run, cancel, reset }`.
  One run at a time: starting a new one aborts the previous, and a response from a superseded
  run is ignored. Program failures (compile error, non-zero exit, timeout) are `done` with a
  result; only service failures (`GlimpseApiError`, `GlimpseNetworkError`, `GlimpseTimeoutError`)
  become `error`.
- **`useLanguages()`** → `{ languages, error, loading, reload }`.
- **`useHealth({ intervalMs? })`** → `{ health, error, loading, reload }`, polled when `intervalMs > 0`.
- **`useGlimpseClient()`** → the provider's `GlimpseClient`, for anything the hooks don't cover.

Every hook accepts `{ client }` to bypass the provider, which also makes them easy to test
with a client built on a fake `fetch`.

## Provider

`<GlimpseProvider baseUrl apiKey headers retry fetch>` builds a client once per `baseUrl` /
`apiKey` pair, or takes a ready-made one via `client`. Leave `apiKey` unset in public
browser apps; public Glimpse instances rely on CORS and rate limits instead.
