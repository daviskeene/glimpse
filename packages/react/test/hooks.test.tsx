import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import {
  GlimpseApiError,
  GlimpseClient,
  GlimpseProvider,
  useGlimpseClient,
  useHealth,
  useLanguages,
  useRun,
} from "../src/index.js";

const RESULT = {
  language: "python",
  phase: "run",
  exit_code: 0,
  timed_out: false,
  stdout: "hi\n",
  stderr: "",
  duration_ms: 5,
  truncated: false,
  compile_stderr: "",
};

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });

/** A fetch whose responses are resolved manually, so tests can observe the running state. */
function deferredFetch() {
  const pending: Array<{ resolve: (r: Response) => void; reject: (e: unknown) => void; url: string }> = [];
  const impl = ((url: string | URL | Request, init?: RequestInit) =>
    new Promise<Response>((resolve, reject) => {
      const entry = { resolve, reject, url: String(url) };
      pending.push(entry);
      init?.signal?.addEventListener("abort", () => {
        const e = new Error("aborted");
        e.name = "AbortError";
        reject(e);
      });
    })) as unknown as typeof fetch;
  return { impl, pending };
}

const clientWith = (impl: typeof fetch) => new GlimpseClient({ baseUrl: "http://t", fetch: impl });

describe("useRun", () => {
  it("moves idle → running → done and returns the execution", async () => {
    const { impl, pending } = deferredFetch();
    const client = clientWith(impl);
    const { result } = renderHook(() => useRun({ client }));
    expect(result.current.status).toBe("idle");

    let promise: Promise<unknown> = Promise.resolve();
    act(() => {
      promise = result.current.run({ language: "py", code: "print('hi')" });
    });
    await waitFor(() => expect(result.current.running).toBe(true));
    expect(pending).toHaveLength(1);
    expect(pending[0].url).toBe("http://t/v1/execute");

    await act(async () => {
      pending[0].resolve(json(200, RESULT, { "server-timing": "run;dur=5, total;dur=9" }));
      await promise;
    });
    expect(result.current.status).toBe("done");
    expect(result.current.result?.stdout).toBe("hi\n");
    expect(result.current.result?.meta.timing).toEqual({ run: 5, total: 9 });
    expect(result.current.finishedAt).not.toBeNull();
  });

  it("cancel() aborts the request and returns to idle", async () => {
    const { impl, pending } = deferredFetch();
    const client = clientWith(impl);
    const { result } = renderHook(() => useRun({ client }));
    let promise: Promise<unknown> = Promise.resolve();
    act(() => {
      promise = result.current.run({ language: "py", code: "1" });
    });
    await waitFor(() => expect(pending).toHaveLength(1));
    await act(async () => {
      result.current.cancel();
      expect(await promise).toBeNull();
    });
    expect(result.current.status).toBe("idle");
    expect(result.current.result).toBeNull();
  });

  it("ignores the response of a run that was superseded", async () => {
    const { impl, pending } = deferredFetch();
    const client = clientWith(impl);
    const { result } = renderHook(() => useRun({ client }));
    let first: Promise<unknown> = Promise.resolve();
    let second: Promise<unknown> = Promise.resolve();
    act(() => {
      first = result.current.run({ language: "py", code: "1" });
    });
    await waitFor(() => expect(pending).toHaveLength(1));
    act(() => {
      second = result.current.run({ language: "py", code: "2" });
    });
    await waitFor(() => expect(pending).toHaveLength(2));
    await act(async () => {
      pending[1].resolve(json(200, { ...RESULT, stdout: "second\n" }));
      expect(await first).toBeNull(); // aborted by the second run
      await second;
    });
    expect(result.current.result?.stdout).toBe("second\n");
  });

  it("surfaces service failures as error state", async () => {
    const { impl, pending } = deferredFetch();
    const client = clientWith(impl);
    const { result } = renderHook(() => useRun({ client }));
    let promise: Promise<unknown> = Promise.resolve();
    act(() => {
      promise = result.current.run({ language: "py", code: "1" });
    });
    await waitFor(() => expect(pending).toHaveLength(1));
    await act(async () => {
      pending[0].resolve(json(503, { error: { code: "no_capacity", message: "busy" } }, { "retry-after": "1" }));
      await promise;
    });
    expect(result.current.status).toBe("error");
    expect(result.current.error).toBeInstanceOf(GlimpseApiError);
    expect((result.current.error as GlimpseApiError).retryAfter).toBe(1);
  });

  it("reset() clears everything", async () => {
    const { impl, pending } = deferredFetch();
    const client = clientWith(impl);
    const { result } = renderHook(() => useRun({ client }));
    let promise: Promise<unknown> = Promise.resolve();
    act(() => {
      promise = result.current.run({ language: "py", code: "1" });
    });
    await waitFor(() => expect(pending).toHaveLength(1));
    await act(async () => {
      pending[0].resolve(json(200, RESULT));
      await promise;
    });
    expect(result.current.status).toBe("done");
    act(() => result.current.reset());
    expect(result.current.status).toBe("idle");
    expect(result.current.result).toBeNull();
  });
});

describe("GlimpseProvider", () => {
  it("supplies a client to hooks and throws without one", async () => {
    const { impl, pending } = deferredFetch();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <GlimpseProvider baseUrl="http://provided" fetch={impl}>
        {children}
      </GlimpseProvider>
    );
    const { result } = renderHook(() => useGlimpseClient(), { wrapper });
    expect(result.current.baseUrl).toBe("http://provided");

    const run = renderHook(() => useRun(), { wrapper });
    act(() => {
      void run.result.current.run({ language: "py", code: "1" });
    });
    await waitFor(() => expect(pending[0]?.url).toBe("http://provided/v1/execute"));

    // React logs the thrown render error; keep the test output clean.
    const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      expect(() => renderHook(() => useGlimpseClient())).toThrow(/GlimpseProvider/);
    } finally {
      quiet.mockRestore();
    }
  });
});

describe("useLanguages and useHealth", () => {
  it("load once and expose the data", async () => {
    const { impl, pending } = deferredFetch();
    const client = clientWith(impl);
    const langs = renderHook(() => useLanguages({ client }));
    const health = renderHook(() => useHealth({ client }));
    expect(langs.result.current.loading).toBe(true);
    await waitFor(() => expect(pending).toHaveLength(2));
    await act(async () => {
      pending.find((p) => p.url.endsWith("/v1/languages"))?.resolve(
        json(200, [{ id: "python", name: "Python", aliases: ["py"], version: "3.12", compiled: false, filename: "main.py", sample: "" }]),
      );
      pending.find((p) => p.url.endsWith("/health"))?.resolve(
        json(200, { status: "ok", runner: "docker", version: "1.0.0", details: { pool_ready: 4 } }),
      );
    });
    await waitFor(() => expect(langs.result.current.loading).toBe(false));
    expect(langs.result.current.languages?.[0].id).toBe("python");
    await waitFor(() => expect(health.result.current.health?.runner).toBe("docker"));
    expect(health.result.current.error).toBeNull();
  });
});
