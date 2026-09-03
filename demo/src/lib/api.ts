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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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
  return (await response.json()) as T;
}

export const execute = (body: ExecuteRequest) =>
  request<ExecuteResponse>("/v1/execute", { method: "POST", body: JSON.stringify(body) });

export const listLanguages = () => request<LanguageInfo[]>("/v1/languages");

export const getHealth = () => request<Health>("/health");
