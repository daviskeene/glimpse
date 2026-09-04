/** Wire types for the Glimpse `/v1` API. Field names match the JSON exactly. */

/** Which phase the process reached. `compile` only appears for compiled languages. */
export type Phase = "compile" | "run";

export interface ExecuteRequest {
  /** Language id or Markdown-fence alias: `python`, `py`, `js`, `ts`, `sh`, `c++`, `rs`, `kt`, ... */
  language: string;
  /** Source code. BOM/CRLF are normalised server-side; Java/Go boilerplate is fixed up. */
  code: string;
  /** Data made available on standard input. */
  stdin?: string;
  /** Wall-clock limit for the run phase in seconds; clamped to the server's maximum. */
  timeout_s?: number;
}

/**
 * The result of a run. Program failures (compile errors, non-zero exits, timeouts) are
 * ordinary results: look at `phase`, `exit_code` and `timed_out`. Only failures of the
 * service itself are thrown as {@link GlimpseApiError} / {@link GlimpseNetworkError}.
 */
export interface ExecuteResponse {
  /** Canonical language id. */
  language: string;
  phase: Phase;
  /** Exit status of the last phase. `137` means killed (timeout, memory or process limit). */
  exit_code: number;
  timed_out: boolean;
  stdout: string;
  stderr: string;
  /** Wall-clock time of the last phase in milliseconds, as measured by the sandbox. */
  duration_ms: number;
  /** True if stdout or stderr exceeded the output cap and was cut. */
  truncated: boolean;
  /** Compiler diagnostics (warnings) when compilation succeeded; empty otherwise. */
  compile_stderr: string;
}

/** Server-side phase timings in milliseconds, from the `Server-Timing` header. */
export interface ServerTiming {
  [phase: string]: number;
}

/** What the client learned about the request beyond the response body. */
export interface ExecutionMeta {
  /** The server's `X-Request-ID` (yours is echoed back if you sent one). */
  requestId: string | null;
  /**
   * Server-side phases (`queue`, `acquire`, `create`, `upload`, `compile`, `run`, `total`),
   * or `null` if the server did not send a `Server-Timing` header.
   */
  timing: ServerTiming | null;
  /** Milliseconds from sending the request to parsing the response, as seen by this client. */
  roundTripMs: number;
}

/** A run result plus request metadata. Spreads the wire fields unchanged and adds `meta`. */
export interface Execution extends ExecuteResponse {
  meta: ExecutionMeta;
}

export interface LanguageInfo {
  id: string;
  name: string;
  aliases: string[];
  /** Toolchain version string, or `null` if the backend cannot probe it. */
  version: string | null;
  compiled: boolean;
  /** File the code is written to in the sandbox. */
  filename: string;
  /** A small program that reads one line from stdin and greets it. */
  sample: string;
}

export interface HealthLimits {
  memory_mb?: number;
  cpus?: number;
  pids?: number;
  tmpfs_mb?: number;
  network?: string;
}

export interface Health {
  status: "ok" | "degraded";
  runner: string;
  version: string;
  details: {
    image?: string;
    pool_ready?: number;
    pool_size?: number;
    in_flight?: number;
    queued?: number;
    max_concurrency?: number;
    queue_size?: number;
    queue_timeout_s?: number;
    limits?: HealthLimits;
    function?: string;
    [key: string]: unknown;
  };
}

/** The body every non-2xx response carries. */
export interface ErrorBody {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}
