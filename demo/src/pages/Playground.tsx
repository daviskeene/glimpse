import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView, keymap } from "@codemirror/view";
import { Prec } from "@codemirror/state";
import { ChevronDown, ChevronRight, Play } from "lucide-react";
import { cn } from "@/lib/utils";
import { API_URL, ApiError, NetworkError, execute, type ExecuteResponse } from "@/lib/api";
import { LANGUAGES, DEFAULT_STDIN, byId } from "@/lib/languages";
import { editorTheme } from "@/lib/editorTheme";
import { describeLimits, useHealth } from "@/lib/health";
import { CopyButton } from "@/components/CodeBlock";

type RunState =
  | { status: "idle" }
  | { status: "running"; startedAt: number }
  | { status: "done"; result: ExecuteResponse; roundTripMs: number }
  | { status: "error"; error: ApiError | NetworkError };

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
const RUN_KEY = isMac ? "⌘↵" : "Ctrl+↵";

function verdict(result: ExecuteResponse): { tone: "ok" | "warn" | "bad"; word: string } {
  if (result.timed_out) return { tone: "warn", word: "timed out" };
  if (result.exit_code === 0) return { tone: "ok", word: "ok" };
  if (result.exit_code === 137) return { tone: "bad", word: "killed" };
  return { tone: "bad", word: result.phase === "compile" ? "compile error" : "failed" };
}

const toneDot = { ok: "bg-mint", warn: "bg-amber", bad: "bg-coral", idle: "bg-mist", running: "bg-amber" };
const toneText = { ok: "text-mint", warn: "text-amber", bad: "text-coral", idle: "text-mist", running: "text-amber" };

function explain(error: ApiError | NetworkError): string {
  if (error instanceof NetworkError) {
    return `${error.message}\n\nStart one locally with:\n  git clone https://github.com/daviskeene/glimpse && cd glimpse\n  docker compose up\n\nor build the demo with VITE_GLIMPSE_API_URL pointing at a running server.`;
  }
  switch (error.code) {
    case "rate_limited":
      return `${error.message}\n\nThe public demo allows a limited number of runs per minute per client.`;
    case "no_capacity":
      return `${error.message}\n\nEvery sandbox is busy right now. Try again in a second${error.retryAfter ? ` (Retry-After: ${error.retryAfter}s)` : ""}.`;
    case "unauthorized":
      return `${error.message}\n\nThis server requires an API key; the demo does not send one.`;
    default:
      return `${error.status} ${error.code}\n${error.message}`;
  }
}

export default function Playground() {
  const [langId, setLangId] = useState(LANGUAGES[0].id);
  const lang = byId(langId);
  const [code, setCode] = useState(lang.samples.hello);
  const [sample, setSample] = useState<"hello" | "timeout" | "custom">("hello");
  const [stdin, setStdin] = useState(DEFAULT_STDIN);
  const [stdinOpen, setStdinOpen] = useState(true);
  const [timeoutS, setTimeoutS] = useState(10);
  const [state, setState] = useState<RunState>({ status: "idle" });
  const [elapsed, setElapsed] = useState(0);
  const [showRaw, setShowRaw] = useState(false);
  const health = useHealth();
  const limits = describeLimits(health);

  // Inputs also live in a ref (refreshed every render, and synchronously for `code` in
  // the editor's onChange) so a keyboard-shortcut run cannot see a stale editor buffer.
  const latest = useRef({ langId, code, stdin, timeoutS });
  latest.current = { langId, code, stdin, timeoutS };
  const inFlight = useRef(false);

  const run = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    const { langId: language, code: source, stdin: input, timeoutS: timeout } = latest.current;
    const startedAt = performance.now();
    setElapsed(0);
    setState({ status: "running", startedAt });
    setShowRaw(false);
    try {
      const result = await execute({ language, code: source, stdin: input, timeout_s: timeout });
      setState({ status: "done", result, roundTripMs: Math.round(performance.now() - startedAt) });
    } catch (err) {
      if (err instanceof ApiError || err instanceof NetworkError) setState({ status: "error", error: err });
      else setState({ status: "error", error: new NetworkError(String(err)) });
    } finally {
      inFlight.current = false;
    }
  }, []);

  const runRef = useRef(run);
  runRef.current = run;

  useEffect(() => {
    if (state.status !== "running") return;
    const { startedAt } = state;
    const id = window.setInterval(() => setElapsed(performance.now() - startedAt), 47);
    return () => window.clearInterval(id);
  }, [state]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // The editor's own keymap handles Mod-Enter (and preventDefault()s it) when focused.
      if (e.defaultPrevented) return;
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        void runRef.current();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const extensions = useMemo(
    () => [
      lang.editor(),
      editorTheme,
      EditorView.lineWrapping,
      Prec.highest(
        keymap.of([
          {
            key: "Mod-Enter",
            run: () => {
              void runRef.current();
              return true;
            },
          },
        ]),
      ),
    ],
    [lang],
  );

  const selectLanguage = (id: string) => {
    if (id === langId) return;
    setLangId(id);
    setCode(byId(id).samples.hello);
    setSample("hello");
    setState({ status: "idle" });
  };

  const loadSample = (kind: "hello" | "timeout") => {
    setCode(lang.samples[kind]);
    setSample(kind);
  };

  const running = state.status === "running";
  const readout = (() => {
    if (state.status === "idle") return { tone: "idle" as const, main: "ready", extra: `${RUN_KEY} to run` };
    if (state.status === "running")
      return { tone: "running" as const, main: "running", extra: `${(elapsed / 1000).toFixed(2)} s` };
    if (state.status === "error") {
      const e = state.error;
      return {
        tone: "bad" as const,
        main: e instanceof ApiError ? `${e.status} ${e.code}` : "unreachable",
        extra: e instanceof ApiError ? undefined : API_URL,
      };
    }
    const r = state.result;
    const v = verdict(r);
    return {
      tone: v.tone,
      main: `${r.phase} · exit ${r.exit_code}`,
      extra: `${r.duration_ms} ms`,
      word: v.word,
      badges: [
        r.truncated ? "output truncated" : null,
        r.phase === "compile" ? "stopped at compile" : null,
      ].filter((b): b is string => !!b),
      roundTrip: state.roundTripMs,
    };
  })();

  return (
    <div className="stagger">
      {/* Hero */}
      <section className="mb-8 max-w-3xl sm:mb-10">
        <h1 className="font-display text-[40px] font-bold leading-[1.02] text-ink sm:text-[60px]">
          Run code you don&rsquo;t trust.
        </h1>
        <p className="mt-4 max-w-xl text-[17px] leading-relaxed text-ink-soft">
          Every request gets a fresh, locked-down sandbox that is destroyed when it finishes.
          Ten languages, one JSON result. Try it below, or read the{" "}
          <a href="/docs" className="text-ink underline decoration-paper-line underline-offset-4 hover:decoration-ink">
            API docs
          </a>
          .
        </p>
      </section>

      {/* Chamber */}
      <section
        aria-label="Playground"
        className="overflow-hidden rounded-xl border border-petrol-line bg-petrol shadow-[0_24px_60px_-30px_rgba(15,42,46,0.6)]"
      >
        {/* Chamber header: file tabs + limits */}
        <div className="flex items-stretch justify-between gap-3 border-b border-petrol-line/70 bg-petrol-2">
          <div role="tablist" aria-label="Language" className="scrollbar-thin flex min-w-0 overflow-x-auto">
            {LANGUAGES.map((l) => {
              const active = l.id === langId;
              return (
                <button
                  key={l.id}
                  role="tab"
                  aria-selected={active}
                  onClick={() => selectLanguage(l.id)}
                  className={cn(
                    "relative shrink-0 px-2.5 py-2.5 font-mono text-[12px] transition-colors sm:px-3",
                    active ? "text-white" : "text-mist hover:text-white",
                  )}
                >
                  {l.file}
                  <span
                    aria-hidden
                    className={cn(
                      "absolute inset-x-3 bottom-0 h-[2px] rounded-full bg-amber transition-transform duration-300",
                      active ? "scale-x-100" : "scale-x-0",
                    )}
                  />
                </button>
              );
            })}
          </div>
          <div className="hidden shrink-0 items-center gap-2 pr-4 font-mono text-[11px] text-mist xl:flex">
            <span className="uppercase tracking-[0.18em] text-mist/70">sandbox</span>
            <span className={cn(limits.tone === "warn" && "text-coral")}>{limits.text}</span>
          </div>
        </div>

        {/* Editor | Output */}
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <div className="flex flex-col border-b border-petrol-line/70 lg:border-b-0 lg:border-r">
            <div className="flex items-center justify-between px-3 pt-2.5">
              <div className="flex gap-1.5">
                {(["hello", "timeout"] as const).map((kind) => (
                  <button
                    key={kind}
                    type="button"
                    onClick={() => loadSample(kind)}
                    className={cn(
                      "rounded-full border px-2.5 py-0.5 font-mono text-[11px] transition-colors",
                      sample === kind
                        ? "border-amber/60 bg-amber/10 text-amber"
                        : "border-petrol-line text-mist hover:border-mist hover:text-white",
                    )}
                  >
                    {kind === "hello" ? "hello sample" : "timeout sample"}
                  </button>
                ))}
              </div>
              <span className="font-mono text-[11px] text-mist/70">{lang.label}</span>
            </div>
            <div className="h-[340px] sm:h-[400px]">
              <CodeMirror
                value={code}
                height="100%"
                theme="none"
                extensions={extensions}
                onChange={(v) => {
                  latest.current.code = v;
                  setCode(v);
                  setSample("custom");
                }}
                basicSetup={{
                  lineNumbers: true,
                  foldGutter: false,
                  highlightActiveLine: true,
                  highlightActiveLineGutter: true,
                  bracketMatching: true,
                  closeBrackets: true,
                  autocompletion: false,
                  indentOnInput: true,
                  tabSize: 4,
                }}
                className="h-full"
                aria-label="Code editor"
              />
            </div>
            <div className="border-t border-petrol-line/70">
              <button
                type="button"
                onClick={() => setStdinOpen((o) => !o)}
                aria-expanded={stdinOpen}
                className="flex w-full items-center gap-1.5 px-3 py-2 font-mono text-[11.5px] text-mist hover:text-white"
              >
                {stdinOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                stdin
                {!stdinOpen && stdin && <span className="ml-2 truncate text-mist/60">{stdin.split("\n")[0]}</span>}
              </button>
              {stdinOpen && (
                <textarea
                  value={stdin}
                  onChange={(e) => setStdin(e.target.value)}
                  spellCheck={false}
                  aria-label="Standard input"
                  placeholder="Text your program reads from standard input"
                  className="block h-[76px] w-full resize-y bg-petrol px-4 py-2 font-mono text-[13px] leading-relaxed text-[#E6EEEC] placeholder:text-mist/50 focus:outline-none"
                />
              )}
            </div>
          </div>

          <div className="flex min-h-[280px] flex-col lg:min-h-0">
            <div className="flex items-center justify-between px-3 pt-2.5">
              <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-mist/70">output</span>
              {state.status === "done" && (
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => setShowRaw((s) => !s)}
                    className={cn(
                      "rounded-md border px-2 py-1 font-mono text-[11px] transition-colors",
                      showRaw
                        ? "border-amber/60 text-amber"
                        : "border-petrol-line text-mist hover:border-mist hover:text-white",
                    )}
                  >
                    {showRaw ? "formatted" : "raw JSON"}
                  </button>
                  <CopyButton
                    text={showRaw ? JSON.stringify(state.result, null, 2) : state.result.stdout}
                    label={showRaw ? "copy JSON" : "copy stdout"}
                  />
                </div>
              )}
            </div>
            <div
              className="scrollbar-thin min-h-0 flex-1 overflow-auto px-4 py-3 font-mono text-[13px] leading-relaxed"
              aria-live="polite"
            >
              {state.status === "idle" && (
                <p className="text-mist/70">
                  Output appears here. Press <span className="text-mist">Run</span> or {RUN_KEY}.
                  <br />
                  <span className="text-mist/50">API: {API_URL}</span>
                </p>
              )}
              {state.status === "running" && <p className="text-mist/70">Creating a sandbox and running {lang.file}…</p>}
              {state.status === "error" && <pre className="whitespace-pre-wrap text-coral">{explain(state.error)}</pre>}
              {state.status === "done" &&
                (showRaw ? (
                  <pre className="whitespace-pre-wrap text-sky">{JSON.stringify(state.result, null, 2)}</pre>
                ) : (
                  <>
                    {state.result.compile_stderr && (
                      <details className="mb-3 rounded-md border border-amber/30 bg-amber/5 text-amber" open>
                        <summary className="cursor-pointer px-3 py-1.5 text-[11px] uppercase tracking-[0.18em] text-amber/80">
                          compiler output
                        </summary>
                        <pre className="whitespace-pre-wrap px-3 pb-2 text-[12.5px]">
                          {state.result.compile_stderr}
                        </pre>
                      </details>
                    )}
                    {state.result.stdout && (
                      <pre className="whitespace-pre-wrap text-[#E6EEEC]">{state.result.stdout}</pre>
                    )}
                    {state.result.stderr && (
                      <pre className="whitespace-pre-wrap text-coral">{state.result.stderr}</pre>
                    )}
                    {!state.result.stdout && !state.result.stderr && (
                      <p className="text-mist/70">(no output)</p>
                    )}
                  </>
                ))}
            </div>
          </div>
        </div>

        {/* Readout strip */}
        <div className="relative flex flex-col gap-3 border-t border-petrol-line bg-petrol-2 px-3 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-4">
          {running && (
            <span
              aria-hidden
              className="pointer-events-none absolute inset-x-0 top-0 h-[2px] overflow-hidden"
            >
              <span className="block h-full w-1/3 animate-sweep bg-gradient-to-r from-transparent via-amber to-transparent" />
            </span>
          )}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void run()}
              disabled={running}
              className="inline-flex items-center gap-2 rounded-md bg-amber px-4 py-2 font-display text-[15px] font-semibold text-petrol transition-[background-color,transform] hover:bg-amber-deep active:scale-[0.98] disabled:cursor-progress disabled:opacity-70"
            >
              <Play className="h-4 w-4 fill-current" />
              {running ? "Running" : "Run"}
              <kbd className="ml-1 hidden rounded border border-petrol/30 px-1.5 font-mono text-[10.5px] font-medium sm:inline">
                {RUN_KEY}
              </kbd>
            </button>
            <label className="flex items-center gap-1.5 font-mono text-[11.5px] text-mist">
              timeout
              <input
                type="number"
                min={1}
                max={30}
                value={timeoutS}
                onChange={(e) => setTimeoutS(Math.max(1, Math.min(30, Number(e.target.value) || 1)))}
                className="w-12 rounded border border-petrol-line bg-petrol px-1.5 py-1 text-center text-[#E6EEEC] focus:border-amber focus:outline-none"
              />
              s
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[12.5px]">
            <span className="flex items-center gap-2">
              <span
                aria-hidden
                className={cn("h-2 w-2 rounded-full", toneDot[readout.tone], running && "animate-pulse")}
              />
              <span className={cn("font-medium", toneText[readout.tone])}>{readout.main}</span>
            </span>
            {readout.extra && <span className="text-[#E6EEEC]">{readout.extra}</span>}
            {"word" in readout && readout.word && readout.word !== "ok" && (
              <span className={cn("rounded-sm border px-1.5 py-px text-[11px]", toneText[readout.tone], "border-current/40")}>
                {readout.word}
              </span>
            )}
            {"badges" in readout &&
              readout.badges?.map((b) => (
                <span key={b} className="rounded-sm border border-mist/40 px-1.5 py-px text-[11px] text-mist">
                  {b}
                </span>
              ))}
            {"roundTrip" in readout && readout.roundTrip !== undefined && (
              <span className="text-mist/70">{(readout.roundTrip / 1000).toFixed(2)} s round trip</span>
            )}
          </div>
        </div>
      </section>

      {/* Process line */}
      <section className="mt-12 sm:mt-16" aria-labelledby="process-heading">
        <h2 id="process-heading" className="font-display text-[22px] font-semibold text-ink sm:text-[26px]">
          What happens when you press Run
        </h2>
        <ol className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {[
            {
              n: 1,
              title: "A sandbox is created",
              body: `A fresh container from the glimpse-sandbox image: ${
                limits.tone === "ok" && health.status === "ok" && health.health.runner === "docker"
                  ? limits.text
                  : "no network, read-only root filesystem, memory, CPU and process limits"
              }, no capabilities, not root.`,
            },
            {
              n: 2,
              title: "Your files go in",
              body: `${lang.file} and your stdin are written to a small tmpfs at /work. Nothing from any previous run exists.`,
            },
            {
              n: 3,
              title: lang.compiled ? "Compile, then run under a hard deadline" : "Run under a hard deadline",
              body: `${lang.compiled ? "The compiler runs first with its own limit. Then " : ""}a supervisor SIGKILLs the whole process group at ${timeoutS}s; the runner kills the container if anything hangs.`,
            },
            {
              n: 4,
              title: "The sandbox is destroyed",
              body: "stdout, stderr, the exit code and timing come back as one JSON object. The container is removed, never reused.",
            },
          ].map((step) => (
            <li key={step.n} className="border-t border-ink/15 pt-4">
              <div className="font-mono text-[11px] text-ink-mute">{String(step.n).padStart(2, "0")}</div>
              <h3 className="mt-1.5 font-display text-[17px] font-semibold text-ink">{step.title}</h3>
              <p className="mt-1.5 text-[14px] leading-relaxed text-ink-soft">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
