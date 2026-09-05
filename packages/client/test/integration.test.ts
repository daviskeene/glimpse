/**
 * Runs against a real Glimpse server when GLIMPSE_TEST_URL is set (CI starts one with the
 * unsafe-local runner). Skipped otherwise, so `npm test` needs no server.
 */
import { describe, expect, it } from "vitest";

import { GlimpseApiError, createClient, isSuccess } from "../src/index.js";

const url = process.env.GLIMPSE_TEST_URL;

describe.skipIf(!url)("against a live server", () => {
  const client = createClient({ baseUrl: url, retry: { maxAttempts: 3 } });

  // The first /v1/languages call makes the server probe every toolchain's version, which
  // can take a few seconds on a cold runner; later calls are cached.
  it("reports health and languages", { timeout: 60_000 }, async () => {
    const health = await client.health();
    expect(health.status).toBe("ok");
    const languages = await client.languages();
    expect(languages.map((l) => l.id)).toContain("python");
  });

  it("runs a Python snippet with stdin and exposes Server-Timing", async () => {
    const run = await client.execute({ language: "py", code: "print(input()[::-1])", stdin: "glimpse" });
    expect(run.language).toBe("python");
    expect(run.stdout).toBe("espmilg\n");
    expect(isSuccess(run)).toBe(true);
    expect(run.meta.requestId).toBeTruthy();
    expect(run.meta.timing).not.toBeNull();
    expect(typeof run.meta.timing?.total).toBe("number");
  });

  it("returns program failures as results", async () => {
    const run = await client.execute({ language: "python", code: "import sys; sys.exit(3)" });
    expect(run.exit_code).toBe(3);
    expect(isSuccess(run)).toBe(false);
  });

  it("maps an unsupported language to a 400 GlimpseApiError", async () => {
    const err = (await client.execute({ language: "cobol", code: "x" }).catch((e: unknown) => e)) as GlimpseApiError;
    expect(err).toBeInstanceOf(GlimpseApiError);
    expect(err.status).toBe(400);
    expect(err.code).toBe("unsupported_language");
  });
});
