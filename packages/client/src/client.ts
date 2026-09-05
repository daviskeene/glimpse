import { GlimpseApiError, GlimpseNetworkError, GlimpseTimeoutError, isAbortError } from "./errors.js";
import { parseServerTiming } from "./timing.js";
import type {
  ErrorBody,
  ExecuteRequest,
  ExecuteResponse,
  Execution,
  Health,
  LanguageInfo,
} from "./types.js";

export const DEFAULT_BASE_URL = "http://localhost:8000";

export interface RetryOptions {
  /**
   * Total attempts for a request, including the first. Only 429 and 503 responses are
   * retried, honouring `Retry-After`; network failures and other statuses are not.
   * Default `1` (no retries).
   */
  maxAttempts?: number;
  /** Longest single wait between attempts, in milliseconds. Default `10000`. */
  maxDelayMs?: number;
}

export interface ClientOptions {
  /** Where the API lives, e.g. `https://api.glimpse.daviskeene.com`. Default `http://localhost:8000`. */
  baseUrl?: string;
  /** Sent as `Authorization: Bearer <key>` when the server has API keys configured. */
  apiKey?: string;
  /** A `fetch` implementation; defaults to the global one. Handy for tests and polyfills. */
  fetch?: typeof fetch;
  /** Extra headers sent with every request. */
  headers?: Record<string, string>;
  /** Retry policy for every request; override per call with `RequestOptions.retry`. */
  retry?: RetryOptions;
}

export interface RequestOptions {
  /** Cancel the request. The promise rejects with the signal's reason (an `AbortError`). */
  signal?: AbortSignal;
  /** Fail with {@link GlimpseTimeoutError} if no response arrives in time. */
  timeoutMs?: number;
  /** Your own `X-Request-ID`; the server echoes it and logs it. */
  requestId?: string;
  retry?: RetryOptions;
}

type FetchLike = typeof fetch;

interface Sent<T> {
  data: T;
  response: Response;
}

const now = (): number =>
  typeof performance !== "undefined" && typeof performance.now === "function"
    ? performance.now()
    : Date.now();

function resolveFetch(custom: FetchLike | undefined): FetchLike {
  if (custom) return custom;
  if (typeof globalThis.fetch === "function") return globalThis.fetch.bind(globalThis);
  throw new Error(
    "No fetch implementation available: pass `fetch` in ClientOptions (Node < 18 needs a polyfill)",
  );
}

async function readErrorBody(
  response: Response,
): Promise<{ code: string; message: string; details?: unknown }> {
  const fallback = {
    code: "http_error",
    message: `${response.status} ${response.statusText}`.trim(),
  };
  let text: string;
  try {
    text = await response.text();
  } catch {
    return fallback;
  }
  try {
    const body = JSON.parse(text) as Partial<ErrorBody>;
    if (body && typeof body === "object" && body.error && typeof body.error === "object") {
      return {
        code: body.error.code ?? fallback.code,
        message: body.error.message ?? fallback.message,
        details: body.error.details,
      };
    }
  } catch {
    /* not JSON */
  }
  return text ? { ...fallback, message: `${fallback.message}: ${text.slice(0, 200)}` } : fallback;
}

function parseRetryAfter(response: Response): number | null {
  const raw = response.headers.get("retry-after");
  if (raw === null) return null;
  const seconds = Number(raw);
  if (Number.isFinite(seconds)) return Math.max(0, seconds);
  const at = Date.parse(raw);
  return Number.isFinite(at) ? Math.max(0, (at - Date.now()) / 1000) : null;
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason);
      return;
    }
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(signal.reason);
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

/** True when a run finished cleanly: exit code 0 and no timeout. */
export function isSuccess(result: ExecuteResponse): boolean {
  return result.exit_code === 0 && !result.timed_out;
}

export class GlimpseClient {
  readonly baseUrl: string;
  private readonly apiKey: string | undefined;
  private readonly fetchImpl: FetchLike;
  private readonly headers: Record<string, string>;
  private readonly retry: Required<RetryOptions>;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.apiKey = options.apiKey;
    this.fetchImpl = resolveFetch(options.fetch);
    this.headers = { ...(options.headers ?? {}) };
    this.retry = {
      maxAttempts: Math.max(1, options.retry?.maxAttempts ?? 1),
      maxDelayMs: options.retry?.maxDelayMs ?? 10_000,
    };
  }

  /**
   * Compile (if needed) and run a snippet. Resolves to the result for *any* program outcome;
   * rejects only when the service fails (`GlimpseApiError`), cannot be reached
   * (`GlimpseNetworkError`), times out client-side (`GlimpseTimeoutError`) or is aborted.
   */
  async execute(input: ExecuteRequest, options: RequestOptions = {}): Promise<Execution> {
    const started = now();
    const { data, response } = await this.send<ExecuteResponse>("POST", "/v1/execute", input, options);
    return {
      ...data,
      meta: {
        requestId: response.headers.get("x-request-id"),
        timing: parseServerTiming(response.headers.get("server-timing")),
        roundTripMs: Math.round(now() - started),
      },
    };
  }

  /** Supported languages, their aliases and (when known) toolchain versions. */
  async languages(options: RequestOptions = {}): Promise<LanguageInfo[]> {
    const { data } = await this.send<LanguageInfo[]>("GET", "/v1/languages", undefined, options);
    return data;
  }

  /** Backend status: runner, pool, limits. Throws `GlimpseApiError` (503) when unhealthy. */
  async health(options: RequestOptions = {}): Promise<Health> {
    const { data } = await this.send<Health>("GET", "/health", undefined, options);
    return data;
  }

  private async send<T>(
    method: "GET" | "POST",
    path: string,
    body: unknown,
    options: RequestOptions,
  ): Promise<Sent<T>> {
    const url = `${this.baseUrl}${path}`;
    const retry: Required<RetryOptions> = {
      maxAttempts: Math.max(1, options.retry?.maxAttempts ?? this.retry.maxAttempts),
      maxDelayMs: options.retry?.maxDelayMs ?? this.retry.maxDelayMs,
    };
    const headers: Record<string, string> = { accept: "application/json", ...this.headers };
    if (body !== undefined) headers["content-type"] = "application/json";
    if (this.apiKey) headers.authorization = `Bearer ${this.apiKey}`;
    if (options.requestId) headers["x-request-id"] = options.requestId;
    // A string body gets a Content-Length automatically; the API refuses chunked POSTs.
    const payload = body === undefined ? undefined : JSON.stringify(body);

    const controller = new AbortController();
    let timedOut = false;
    const forwardAbort = () => controller.abort(options.signal?.reason);
    if (options.signal) {
      if (options.signal.aborted) throw options.signal.reason ?? abortError();
      options.signal.addEventListener("abort", forwardAbort, { once: true });
    }
    const timer =
      options.timeoutMs !== undefined
        ? setTimeout(() => {
            timedOut = true;
            controller.abort();
          }, options.timeoutMs)
        : undefined;

    try {
      for (let attempt = 1; ; attempt++) {
        let response: Response;
        try {
          response = await this.fetchImpl(url, {
            method,
            headers,
            body: payload,
            signal: controller.signal,
          });
        } catch (err) {
          if (timedOut) throw new GlimpseTimeoutError(options.timeoutMs as number);
          if (controller.signal.aborted || isAbortError(err)) throw err;
          throw new GlimpseNetworkError(url, err);
        }

        if (response.ok) {
          const data = (await response.json()) as T;
          return { data, response };
        }

        const { code, message, details } = await readErrorBody(response);
        const error = new GlimpseApiError(response.status, code, message, {
          details,
          retryAfter: parseRetryAfter(response),
          requestId: response.headers.get("x-request-id"),
        });
        if (!error.retryable || attempt >= retry.maxAttempts) throw error;
        const backoff = 250 * 2 ** (attempt - 1);
        const wait = Math.min(
          error.retryAfter !== null ? error.retryAfter * 1000 : backoff,
          retry.maxDelayMs,
        );
        try {
          await sleep(wait, controller.signal);
        } catch (err) {
          if (timedOut) throw new GlimpseTimeoutError(options.timeoutMs as number);
          throw err ?? abortError();
        }
      }
    } finally {
      if (timer !== undefined) clearTimeout(timer);
      options.signal?.removeEventListener("abort", forwardAbort);
    }
  }
}

/** Shorthand for `new GlimpseClient(options)`. */
export function createClient(options: ClientOptions = {}): GlimpseClient {
  return new GlimpseClient(options);
}

function abortError(): Error {
  const err = new Error("The operation was aborted");
  err.name = "AbortError";
  return err;
}
