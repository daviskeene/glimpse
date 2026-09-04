import { describe, expect, it, vi } from "vitest";

import {
  GlimpseApiError,
  GlimpseClient,
  GlimpseNetworkError,
  GlimpseTimeoutError,
  createClient,
  isSuccess,
  parseServerTiming,
} from "../src/index.js";

const RESULT = {
  language: "python",
  phase: "run",
  exit_code: 0,
  timed_out: false,
  stdout: "1\n",
  stderr: "",
  duration_ms: 42,
  truncated: false,
  compile_stderr: "",
};

type Call = { url: string; init: RequestInit };

/** A fetch stand-in that answers with the given responses in order and records every call. */
function fakeFetch(...responses: Array<Response | (() => Response) | Error>) {
  const calls: Call[] = [];
  const impl = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} });
    const next = responses.shift();
    if (next === undefined) throw new Error("fakeFetch: no response queued");
    if (next instanceof Error) throw next;
    return typeof next === "function" ? next() : next;
  }) as unknown as typeof fetch;
  return { impl, calls };
}

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });

describe("execute", () => {
  it("posts JSON and returns the result with request metadata", async () => {
    const { impl, calls } = fakeFetch(
      json(200, RESULT, {
        "x-request-id": "abc123",
        "server-timing": "queue;dur=0, acquire;dur=1, upload;dur=98, run;dur=140, total;dur=281",
      }),
    );
    const client = createClient({ baseUrl: "https://api.example.test/", apiKey: "k1", fetch: impl });

    const run = await client.execute({ language: "py", code: "print(1)", stdin: "x" });

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("https://api.example.test/v1/execute");
    expect(calls[0].init.method).toBe("POST");
    const headers = calls[0].init.headers as Record<string, string>;
    expect(headers["content-type"]).toBe("application/json");
    expect(headers.authorization).toBe("Bearer k1");
    expect(JSON.parse(calls[0].init.body as string)).toEqual({
      language: "py",
      code: "print(1)",
      stdin: "x",
    });
    expect(run.stdout).toBe("1\n");
    expect(run.exit_code).toBe(0);
    expect(isSuccess(run)).toBe(true);
    expect(run.meta.requestId).toBe("abc123");
    expect(run.meta.timing).toEqual({ queue: 0, acquire: 1, upload: 98, run: 140, total: 281 });
    expect(run.meta.roundTripMs).toBeGreaterThanOrEqual(0);
  });

  it("treats program failures as results, not errors", async () => {
    const failed = { ...RESULT, phase: "compile", exit_code: 1, stderr: "error: expected ';'" };
    const { impl } = fakeFetch(json(200, failed));
    const run = await new GlimpseClient({ fetch: impl }).execute({ language: "c", code: "int main(){" });
    expect(run.phase).toBe("compile");
    expect(isSuccess(run)).toBe(false);
    expect(run.meta.timing).toBeNull();
  });

  it("maps error bodies to GlimpseApiError with code, Retry-After and request id", async () => {
    const { impl } = fakeFetch(
      json(
        503,
        { error: { code: "no_capacity", message: "at capacity; retry shortly" } },
        { "retry-after": "1", "x-request-id": "req9" },
      ),
    );
    const err = await new GlimpseClient({ fetch: impl })
      .execute({ language: "python", code: "1" })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(GlimpseApiError);
    const apiErr = err as GlimpseApiError;
    expect(apiErr.status).toBe(503);
    expect(apiErr.code).toBe("no_capacity");
    expect(apiErr.message).toBe("at capacity; retry shortly");
    expect(apiErr.retryAfter).toBe(1);
    expect(apiErr.requestId).toBe("req9");
    expect(apiErr.retryable).toBe(true);
  });

  it("falls back to http_error for non-JSON error bodies", async () => {
    const { impl } = fakeFetch(new Response("<html>bad gateway</html>", { status: 502, statusText: "Bad Gateway" }));
    const err = (await new GlimpseClient({ fetch: impl })
      .execute({ language: "python", code: "1" })
      .catch((e: unknown) => e)) as GlimpseApiError;
    expect(err).toBeInstanceOf(GlimpseApiError);
    expect(err.status).toBe(502);
    expect(err.code).toBe("http_error");
    expect(err.message).toContain("502 Bad Gateway");
    expect(err.retryable).toBe(false);
  });

  it("wraps connection failures in GlimpseNetworkError", async () => {
    const { impl } = fakeFetch(new TypeError("fetch failed"));
    const err = await new GlimpseClient({ baseUrl: "http://127.0.0.1:1", fetch: impl })
      .execute({ language: "python", code: "1" })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(GlimpseNetworkError);
    expect((err as Error).message).toContain("http://127.0.0.1:1");
  });

  it("retries 429/503 up to maxAttempts, honouring Retry-After", async () => {
    const { impl, calls } = fakeFetch(
      json(503, { error: { code: "no_capacity", message: "busy" } }, { "retry-after": "0" }),
      json(429, { error: { code: "rate_limited", message: "slow down" } }, { "retry-after": "0" }),
      json(200, RESULT),
    );
    const client = new GlimpseClient({ fetch: impl, retry: { maxAttempts: 3 } });
    const run = await client.execute({ language: "python", code: "print(1)" });
    expect(run.stdout).toBe("1\n");
    expect(calls).toHaveLength(3);
  });

  it("does not retry by default, nor on non-retryable statuses", async () => {
    const { impl, calls } = fakeFetch(
      json(400, { error: { code: "unsupported_language", message: "no such language" } }),
      json(200, RESULT),
    );
    const err = (await new GlimpseClient({ fetch: impl, retry: { maxAttempts: 5 } })
      .execute({ language: "cobol", code: "x" })
      .catch((e: unknown) => e)) as GlimpseApiError;
    expect(err.code).toBe("unsupported_language");
    expect(calls).toHaveLength(1);
  });

  it("rejects immediately with an AbortError when the signal is already aborted", async () => {
    const { impl, calls } = fakeFetch(json(200, RESULT));
    const controller = new AbortController();
    controller.abort();
    const err = (await new GlimpseClient({ fetch: impl })
      .execute({ language: "python", code: "1" }, { signal: controller.signal })
      .catch((e: unknown) => e)) as Error;
    expect(err.name).toBe("AbortError");
    expect(calls).toHaveLength(0);
  });

  it("fails with GlimpseTimeoutError when timeoutMs elapses", async () => {
    const hanging = vi.fn(
      (_url: string | URL | Request, init?: RequestInit) =>
        new Promise<Response>((_, reject) => {
          init?.signal?.addEventListener("abort", () => {
            const e = new Error("aborted");
            e.name = "AbortError";
            reject(e);
          });
        }),
    ) as unknown as typeof fetch;
    const err = await new GlimpseClient({ fetch: hanging })
      .execute({ language: "python", code: "1" }, { timeoutMs: 20 })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(GlimpseTimeoutError);
    expect((err as GlimpseTimeoutError).timeoutMs).toBe(20);
  });

  it("sends a caller-supplied X-Request-ID and extra headers", async () => {
    const { impl, calls } = fakeFetch(json(200, RESULT));
    const client = new GlimpseClient({ fetch: impl, headers: { "x-app": "demo" } });
    await client.execute({ language: "python", code: "1" }, { requestId: "mine-1" });
    const headers = calls[0].init.headers as Record<string, string>;
    expect(headers["x-request-id"]).toBe("mine-1");
    expect(headers["x-app"]).toBe("demo");
    expect(headers.authorization).toBeUndefined();
  });
});

describe("languages and health", () => {
  it("GETs /v1/languages", async () => {
    const langs = [{ id: "python", name: "Python", aliases: ["py"], version: "3.12", compiled: false, filename: "main.py", sample: "" }];
    const { impl, calls } = fakeFetch(json(200, langs));
    const got = await new GlimpseClient({ baseUrl: "http://h:8000", fetch: impl }).languages();
    expect(got).toEqual(langs);
    expect(calls[0].url).toBe("http://h:8000/v1/languages");
    expect(calls[0].init.method).toBe("GET");
    expect(calls[0].init.body).toBeUndefined();
  });

  it("GETs /health and surfaces 503 unhealthy as GlimpseApiError", async () => {
    const { impl } = fakeFetch(
      json(200, { status: "ok", runner: "docker", version: "1.0.0", details: { pool_ready: 2 } }),
      json(503, { error: { code: "unhealthy", message: "docker daemon unreachable" } }),
    );
    const client = new GlimpseClient({ fetch: impl });
    expect((await client.health()).runner).toBe("docker");
    const err = (await client.health().catch((e: unknown) => e)) as GlimpseApiError;
    expect(err.code).toBe("unhealthy");
  });
});

describe("parseServerTiming", () => {
  it("parses phases in order and ignores junk", () => {
    expect(parseServerTiming("queue;dur=0, upload;dur=98.5, cache;desc=hit, total;dur=281")).toEqual({
      queue: 0,
      upload: 98.5,
      total: 281,
    });
    expect(parseServerTiming("")).toBeNull();
    expect(parseServerTiming(null)).toBeNull();
    expect(parseServerTiming("nonsense")).toBeNull();
  });
});
