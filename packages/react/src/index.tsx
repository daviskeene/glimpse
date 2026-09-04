import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  GlimpseClient,
  createClient,
  isAbortError,
  type ClientOptions,
  type ExecuteRequest,
  type Execution,
  type Health,
  type LanguageInfo,
  type RequestOptions,
} from "@glimpse-run/client";

export type {
  ClientOptions,
  ExecuteRequest,
  ExecuteResponse,
  Execution,
  ExecutionMeta,
  Health,
  LanguageInfo,
  RequestOptions,
  ServerTiming,
} from "@glimpse-run/client";
export {
  GlimpseApiError,
  GlimpseClient,
  GlimpseError,
  GlimpseNetworkError,
  GlimpseTimeoutError,
  createClient,
  isSuccess,
} from "@glimpse-run/client";

const GlimpseContext = createContext<GlimpseClient | null>(null);

export interface GlimpseProviderProps extends ClientOptions {
  /** A pre-built client. When given, the other options are ignored. */
  client?: GlimpseClient;
  children?: ReactNode;
}

/**
 * Makes a Glimpse client available to the hooks below.
 *
 * ```tsx
 * <GlimpseProvider baseUrl="https://api.glimpse.daviskeene.com">{children}</GlimpseProvider>
 * ```
 *
 * The client is created once per `baseUrl` / `apiKey` pair; changing `headers`, `retry` or
 * `fetch` alone does not rebuild it. Pass `client` if you need full control.
 */
export function GlimpseProvider({ client, children, ...options }: GlimpseProviderProps) {
  const latest = useRef(options);
  latest.current = options;
  const { baseUrl, apiKey } = options;
  const value = useMemo(
    () => client ?? createClient({ ...latest.current, baseUrl, apiKey }),
    [client, baseUrl, apiKey],
  );
  return <GlimpseContext.Provider value={value}>{children}</GlimpseContext.Provider>;
}

/** The client from the nearest `GlimpseProvider`. Throws when there is none. */
export function useGlimpseClient(): GlimpseClient {
  const client = useContext(GlimpseContext);
  if (!client) {
    throw new Error(
      "No Glimpse client: wrap your tree in <GlimpseProvider> or pass { client } to the hook",
    );
  }
  return client;
}

function useResolvedClient(explicit: GlimpseClient | undefined): GlimpseClient {
  const fromContext = useContext(GlimpseContext);
  const client = explicit ?? fromContext;
  if (!client) {
    throw new Error(
      "No Glimpse client: wrap your tree in <GlimpseProvider> or pass { client } to the hook",
    );
  }
  return client;
}

const now = (): number =>
  typeof performance !== "undefined" && typeof performance.now === "function"
    ? performance.now()
    : Date.now();

const toError = (err: unknown): Error => (err instanceof Error ? err : new Error(String(err)));

export type RunStatus = "idle" | "running" | "done" | "error";

export interface RunState {
  status: RunStatus;
  /** The execution once `status` is `done`; program failures are still results. */
  result: Execution | null;
  /** Set when `status` is `error`: the service failed, not the program. */
  error: Error | null;
  /** `performance.now()` when the current or last run started. */
  startedAt: number | null;
  /** `performance.now()` when it finished (done or error). */
  finishedAt: number | null;
}

export interface UseRunOptions {
  /** Overrides the provider's client. */
  client?: GlimpseClient;
  /** Applied to every `run()`; the hook manages the `signal` itself. */
  requestOptions?: Omit<RequestOptions, "signal">;
}

export interface UseRun extends RunState {
  /** Start a run; a run already in flight is cancelled first. Resolves to `null` on error or cancel. */
  run: (input: ExecuteRequest) => Promise<Execution | null>;
  /** Abort the run in flight, returning to `idle`. */
  cancel: () => void;
  /** Cancel and clear the result and error. */
  reset: () => void;
  running: boolean;
}

const IDLE: RunState = { status: "idle", result: null, error: null, startedAt: null, finishedAt: null };

/**
 * One run at a time with cancellation and stale-response protection.
 *
 * ```tsx
 * const { run, running, result, error } = useRun();
 * <button onClick={() => run({ language: "py", code })} disabled={running}>Run</button>
 * {result && <pre>{result.stdout}</pre>}
 * ```
 */
export function useRun(options: UseRunOptions = {}): UseRun {
  const client = useResolvedClient(options.client);
  const [state, setState] = useState<RunState>(IDLE);
  const controllerRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);
  const requestOptionsRef = useRef(options.requestOptions);
  requestOptionsRef.current = options.requestOptions;

  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, []);

  const run = useCallback(
    async (input: ExecuteRequest): Promise<Execution | null> => {
      cancel();
      const seq = ++seqRef.current;
      const controller = new AbortController();
      controllerRef.current = controller;
      const startedAt = now();
      setState({ status: "running", result: null, error: null, startedAt, finishedAt: null });
      try {
        const execution = await client.execute(input, {
          ...requestOptionsRef.current,
          signal: controller.signal,
        });
        if (seq !== seqRef.current) return null; // superseded by a newer run
        setState({ status: "done", result: execution, error: null, startedAt, finishedAt: now() });
        return execution;
      } catch (err) {
        if (seq !== seqRef.current) return null;
        if (controller.signal.aborted || isAbortError(err)) {
          setState(IDLE);
          return null;
        }
        setState({ status: "error", result: null, error: toError(err), startedAt, finishedAt: now() });
        return null;
      } finally {
        if (controllerRef.current === controller) controllerRef.current = null;
      }
    },
    [client, cancel],
  );

  const reset = useCallback(() => {
    cancel();
    seqRef.current++;
    setState(IDLE);
  }, [cancel]);

  useEffect(
    () => () => {
      controllerRef.current?.abort();
      seqRef.current++;
    },
    [],
  );

  return { ...state, run, cancel, reset, running: state.status === "running" };
}

export interface UseLanguages {
  languages: LanguageInfo[] | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
}

/** The server's language list, fetched once per client (call `reload()` to refetch). */
export function useLanguages(options: { client?: GlimpseClient } = {}): UseLanguages {
  const client = useResolvedClient(options.client);
  const [languages, setLanguages] = useState<LanguageInfo[] | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    client
      .languages({ signal: controller.signal })
      .then((list) => {
        if (!active) return;
        setLanguages(list);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active && !isAbortError(err)) setError(toError(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [client, generation]);

  const reload = useCallback(() => setGeneration((g) => g + 1), []);
  return { languages, error, loading, reload };
}

export interface UseHealth {
  health: Health | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
}

/**
 * Backend health, optionally polled every `intervalMs`. A `503 unhealthy` response surfaces
 * as `error` (a `GlimpseApiError`), as does an unreachable server.
 */
export function useHealth(options: { client?: GlimpseClient; intervalMs?: number } = {}): UseHealth {
  const client = useResolvedClient(options.client);
  const intervalMs = options.intervalMs ?? 0;
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const load = () =>
      client
        .health({ signal: controller.signal })
        .then((h) => {
          if (!active) return;
          setHealth(h);
          setError(null);
        })
        .catch((err: unknown) => {
          if (active && !isAbortError(err)) setError(toError(err));
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    void load();
    const timer = intervalMs > 0 ? setInterval(() => void load(), intervalMs) : undefined;
    return () => {
      active = false;
      controller.abort();
      if (timer !== undefined) clearInterval(timer);
    };
  }, [client, intervalMs, generation]);

  const reload = useCallback(() => setGeneration((g) => g + 1), []);
  return { health, error, loading, reload };
}
