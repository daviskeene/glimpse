/** Base class for everything this client throws (besides `AbortError` when you cancel). */
export class GlimpseError extends Error {
  /** The underlying error, when there is one (e.g. the `TypeError` fetch threw). */
  readonly cause?: unknown;

  constructor(message: string, options?: { cause?: unknown }) {
    super(message);
    this.name = "GlimpseError";
    if (options?.cause !== undefined) this.cause = options.cause;
  }
}

/**
 * The server answered with an error status. `code` is the stable machine-readable code from
 * the response body (`rate_limited`, `no_capacity`, `unsupported_language`, `code_too_large`,
 * `unauthorized`, `validation_error`, `runner_error`, ...). Program failures are *not* errors:
 * a compile error or a non-zero exit comes back as a normal result.
 */
export class GlimpseApiError extends GlimpseError {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  /** Seconds to wait before retrying, from the `Retry-After` header (429 and 503). */
  readonly retryAfter: number | null;
  readonly requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    options: { details?: unknown; retryAfter?: number | null; requestId?: string | null } = {},
  ) {
    super(message);
    this.name = "GlimpseApiError";
    this.status = status;
    this.code = code;
    this.details = options.details;
    this.retryAfter = options.retryAfter ?? null;
    this.requestId = options.requestId ?? null;
  }

  /** True for 429 and 503: the server explicitly asked you to try again later. */
  get retryable(): boolean {
    return this.status === 429 || this.status === 503;
  }
}

/** The request never produced a response: DNS, connection refused, TLS, CORS, offline. */
export class GlimpseNetworkError extends GlimpseError {
  readonly url: string;

  constructor(url: string, cause: unknown) {
    const reason = cause instanceof Error ? cause.message : String(cause);
    super(`Could not reach the Glimpse API at ${url}: ${reason}`, { cause });
    this.name = "GlimpseNetworkError";
    this.url = url;
  }
}

/** The client-side `timeoutMs` elapsed before a response arrived. */
export class GlimpseTimeoutError extends GlimpseError {
  readonly timeoutMs: number;

  constructor(timeoutMs: number) {
    super(`Glimpse request timed out after ${timeoutMs} ms`);
    this.name = "GlimpseTimeoutError";
    this.timeoutMs = timeoutMs;
  }
}

/** True if `err` is the `AbortError` fetch throws when a signal fires. */
export function isAbortError(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "name" in err &&
    (err as { name: unknown }).name === "AbortError"
  );
}
