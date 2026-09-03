/** Minimal typed client for the Glimpse `/v1` API. */

const raw = import.meta.env.VITE_GLIMPSE_API_URL as string | undefined;
export const API_URL = (raw && raw.trim() ? raw.trim() : "http://localhost:8000").replace(/\/+$/, "");

export interface ExecuteRequest {
  language: string;
  code: string;
  stdin?: string;
  timeout_s?: number;
}

export interface ExecuteResponse {
  language: string;
  phase: "compile" | "run";
  exit_code: number;
  timed_out: boolean;
  stdout: string;
  stderr: string;
  duration_ms: number;
  truncated: boolean;
  /** Compiler diagnostics (warnings) when compilation succeeded. */
  compile_stderr?: string;
}

/** Server-side phase timings from the `Server-Timing` header, in milliseconds. */
export interface ServerTiming {
  [phase: string]: number;
}

/** Parse `queue;dur=0, upload;dur=98, ..., total;dur=281` into phase → ms (order kept). */
export function parseServerTiming(header: string | null): ServerTiming | null {
  if (!header) return null;
  const timing: ServerTiming = {};
  for (const entry of header.split(",")) {
    const [name, ...params] = entry.trim().split(";");
    const dur = params.map((p) => p.trim()).find((p) => p.startsWith("dur="));
    if (!name || !dur) continue;
    const ms = Number(dur.slice(4));
    if (Number.isFinite(ms)) timing[name] = ms;
  }
  return Object.keys(timing).length ? timing : null;
}

export interface ExecuteOutcome {
  result: ExecuteResponse;
  /** Present when the server sent a `Server-Timing` header. */
  timing: ServerTiming | null;
}

export interface LanguageInfo {
  id: string;
  name: string;
  aliases: string[];
  version: string | null;
  compiled: boolean;
  filename?: string;
  sample?: string;
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
    pool_ready?: number;
    pool_size?: number;
    in_flight?: number;
    max_concurrency?: number;
    limits?: HealthLimits;
    function?: string;
    [key: string]: unknown;
  };
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NetworkError";
  }
}

async function send<T>(path: string, init?: RequestInit): Promise<{ data: T; response: Response }> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new NetworkError(`Could not reach the API at ${API_URL}.`);
  }
  if (!response.ok) {
    let code = "http_error";
    let message = `${response.status} ${response.statusText}`.trim();
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string } };
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
      }
    } catch {
      /* non-JSON error body */
    }
    const retry = response.headers.get("retry-after");
    throw new ApiError(response.status, code, message, retry ? Number(retry) : undefined);
  }
  return { data: (await response.json()) as T, response };
}

const request = <T,>(path: string, init?: RequestInit): Promise<T> => send<T>(path, init).then((r) => r.data);

export async function execute(body: ExecuteRequest): Promise<ExecuteOutcome> {
  const { data, response } = await send<ExecuteResponse>("/v1/execute", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return { result: data, timing: parseServerTiming(response.headers.get("server-timing")) };
}

export const listLanguages = () => request<LanguageInfo[]>("/v1/languages");

export const getHealth = () => request<Health>("/health");
