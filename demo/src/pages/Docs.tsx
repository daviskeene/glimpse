import { useState } from "react";
import { useLanguages } from "@glimpse-run/react";
import { cn } from "@/lib/utils";
import { API_URL } from "@/lib/api";
import { LANGUAGES } from "@/lib/languages";
import { describeLimits, useHealth } from "@/lib/health";
import CodeBlock from "@/components/CodeBlock";

const SECTIONS = [
  ["overview", "Overview"],
  ["quickstart", "Quick start"],
  ["execute", "POST /v1/execute"],
  ["errors", "Errors"],
  ["languages", "Languages"],
  ["limits", "Limits"],
  ["security", "Security model"],
  ["self-host", "Self-hosting"],
] as const;

const snippets = {
  curl: `curl -s ${API_URL}/v1/execute \\
  -H 'content-type: application/json' \\
  -d '{"language": "python", "code": "print(input()[::-1])", "stdin": "glimpse"}'`,
  python: `# pip install "glimpse @ git+https://github.com/daviskeene/glimpse"
from glimpse.client import GlimpseClient

with GlimpseClient("${API_URL}") as client:
    result = client.execute("python", "print(input()[::-1])", stdin="glimpse")
    print(result.stdout)        # "espmilg\\n"
    print(result.exit_code)     # 0`,
  javascript: `const res = await fetch("${API_URL}/v1/execute", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ language: "python", code: "print(input()[::-1])", stdin: "glimpse" }),
});
const result = await res.json();
console.log(result.stdout, result.exit_code);`,
  cli: `# from a checkout: uv sync
uv run glimpse run hello.go --url ${API_URL}
uv run glimpse run --lang py - < script.py
uv run glimpse languages`,
};

const response = `{
  "language": "python",
  "phase": "run",
  "exit_code": 0,
  "timed_out": false,
  "stdout": "espmilg\\n",
  "stderr": "",
  "duration_ms": 38,
  "truncated": false
}`;

const compileError = `{
  "language": "c",
  "phase": "compile",
  "exit_code": 1,
  "timed_out": false,
  "stdout": "",
  "stderr": "/work/main.c:1:10: error: expected declaration specifiers ...",
  "duration_ms": 21,
  "truncated": false
}`;

const errorShape = `{
  "error": {
    "code": "rate_limited",
    "message": "rate limit exceeded (30/minute); retry in 12s"
  }
}`;

function Table({ head, rows }: { head: string[]; rows: (string | JSX.Element)[][] }) {
  return (
    <div className="scrollbar-thin overflow-x-auto rounded-lg border border-paper-line bg-white/40">
      <table className="w-full min-w-[520px] text-left text-[13.5px]">
        <thead>
          <tr className="border-b border-paper-line font-mono text-[11px] uppercase tracking-[0.14em] text-ink-mute">
            {head.map((h) => (
              <th key={h} className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-paper-line/60 last:border-0">
              {row.map((cell, j) => (
                <td key={j} className={cn("px-3 py-2 align-top text-ink-soft", j === 0 && "font-mono text-ink")}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24">
      <h2 className="font-display text-[26px] font-semibold text-ink">{title}</h2>
      <div className="mt-4 space-y-4 text-[15px] leading-relaxed text-ink-soft">{children}</div>
    </section>
  );
}

const Code = ({ children }: { children: React.ReactNode }) => (
  <code className="rounded bg-paper-deep px-1 py-0.5 font-mono text-[12.5px] text-ink">{children}</code>
);

export default function Docs() {
  const [tab, setTab] = useState<keyof typeof snippets>("curl");
  const { languages: live } = useLanguages();
  const health = useHealth();
  const limits = describeLimits(health);

  const languageRows = LANGUAGES.map((l) => {
    const info = live?.find((x) => x.id === l.id);
    return [
      l.id,
      l.file,
      info?.aliases.length ? info.aliases.join(", ") : "—",
      info?.version ?? (live ? "—" : "…"),
    ];
  });

  return (
    <div className="grid gap-10 lg:grid-cols-[200px_minmax(0,1fr)]">
      <aside className="lg:sticky lg:top-20 lg:self-start">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-mute">Contents</p>
        <nav className="scrollbar-thin mt-3 flex gap-1 overflow-x-auto lg:flex-col">
          {SECTIONS.map(([id, label]) => (
            <a
              key={id}
              href={`#${id}`}
              className="shrink-0 rounded-md px-2 py-1 text-[13.5px] text-ink-soft hover:bg-paper-deep hover:text-ink"
            >
              {label}
            </a>
          ))}
        </nav>
      </aside>

      <div className="min-w-0 space-y-14">
        <header>
          <h1 className="font-display text-[36px] font-bold leading-tight text-ink sm:text-[44px]">API reference</h1>
          <p className="mt-3 max-w-2xl text-[16px] leading-relaxed text-ink-soft">
            One endpoint runs code; one lists languages; one reports health. Program failures are
            results, not errors. Everything on this page is generated from the API this demo is
            pointed at: <Code>{API_URL}</Code>.
          </p>
        </header>

        <Section id="overview" title="Overview">
          <p>
            Glimpse is an HTTP service that compiles and runs a code snippet inside an isolated
            sandbox and returns what happened. It is meant for agents, playgrounds and graders that
            need to execute code they did not write.
          </p>
          <Table
            head={["Endpoint", "Purpose"]}
            rows={[
              ["POST /v1/execute", "Compile (if needed) and run a snippet; returns stdout, stderr, exit code and timing."],
              ["GET /v1/languages", "Supported language ids, aliases and toolchain versions."],
              ["GET /health", "Backend status: runner type, warm pool, in-flight executions, limits."],
              ["GET /docs", "Interactive OpenAPI documentation served by the API itself."],
            ]}
          />
          <p>
            Status of this server:{" "}
            <span className="font-mono text-ink">
              {health.status === "ok"
                ? `${health.health.runner} · v${health.health.version} · ${limits.text}`
                : health.status === "loading"
                  ? "checking…"
                  : "unreachable"}
            </span>
          </p>
        </Section>

        <Section id="quickstart" title="Quick start">
          <div className="flex gap-1 border-b border-paper-line">
            {(Object.keys(snippets) as (keyof typeof snippets)[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setTab(k)}
                className={cn(
                  "-mb-px border-b-2 px-3 py-2 font-mono text-[12.5px] transition-colors",
                  tab === k ? "border-amber-deep text-ink" : "border-transparent text-ink-mute hover:text-ink",
                )}
              >
                {k === "cli" ? "glimpse CLI" : k}
              </button>
            ))}
          </div>
          <CodeBlock code={snippets[tab]} title={tab === "cli" ? "shell" : tab} />
          <p>Response:</p>
          <CodeBlock code={response} title="200 OK" />
        </Section>

        <Section id="execute" title="POST /v1/execute">
          <p>Request body (JSON; unknown fields are rejected):</p>
          <Table
            head={["Field", "Type", "Notes"]}
            rows={[
              ["language", "string", "Id or alias, case-insensitive. See Languages."],
              ["code", "string", "Required, non-empty, up to 64 KiB. A leading BOM is removed and CRLF line endings are normalised."],
              ["stdin", "string", "Optional, up to 64 KiB. Available on standard input."],
              ["timeout_s", "number", "Optional, 1–30. Wall-clock limit for the run phase (default 10)."],
            ]}
          />
          <p>Response fields:</p>
          <Table
            head={["Field", "Meaning"]}
            rows={[
              ["language", "Canonical id (\"py\" becomes \"python\")."],
              ["phase", "\"compile\" if the compiler failed or timed out, otherwise \"run\"."],
              [
                "exit_code",
                "Exit status of that phase. 137 means killed by SIGKILL: the timeout, the memory limit or the process limit — stderr says which is likely.",
              ],
              ["timed_out", "true if the phase hit its time limit."],
              ["stdout, stderr", "UTF-8 text, each capped at 64 KiB."],
              ["truncated", "true if either stream was cut at the cap. Programs that flood far beyond it are killed."],
              ["compile_stderr", "Compiler warnings when compilation succeeded; empty otherwise."],
              ["duration_ms", "Wall-clock time of that phase in milliseconds."],
            ]}
          />
          <p>
            <strong className="font-medium text-ink">Program failures are 200s.</strong> A compile
            error, an uncaught exception, a non-zero exit or a timeout all come back as a normal
            result. Only failures of the service itself use error status codes.
          </p>
          <CodeBlock code={compileError} title="200 OK — compile error" />
        </Section>

        <Section id="errors" title="Errors">
          <p>Every non-2xx response has the same shape, with a stable machine-readable code:</p>
          <CodeBlock code={errorShape} title="429 Too Many Requests" />
          <Table
            head={["Status", "code", "When"]}
            rows={[
              ["400", "unsupported_language", "Unknown language id or alias; the message lists the supported ones."],
              ["401", "unauthorized", "The server requires an API key (Authorization: Bearer …) and none or a wrong one was sent."],
              ["413", "code_too_large · stdin_too_large · payload_too_large", "A size limit was exceeded."],
              ["422", "validation_error", "Malformed request; details lists the offending fields."],
              ["429", "rate_limited", "Per-client limit hit. Honour the Retry-After header."],
              ["503", "no_capacity", "Every sandbox stayed busy for the whole queue window (a couple of seconds). Honour Retry-After and try again."],
              ["500", "runner_error", "The execution backend failed."],
            ]}
          />
          <p>
            Every response carries an <Code>X-Request-ID</Code> header (yours is echoed back if you send one).
            Successful runs also carry <Code>Server-Timing</Code> with the server-side phases in milliseconds
            (<Code>queue</Code>, <Code>acquire</Code>, <Code>upload</Code>, <Code>compile</Code>, <Code>run</Code>,{" "}
            <Code>total</Code>); DevTools lists them in the request&rsquo;s Timing tab.
          </p>
        </Section>

        <Section id="languages" title="Languages">
          <p>
            Ids and aliases are accepted case-insensitively; the canonical id is echoed in the result.
            Versions below come live from <Code>GET /v1/languages</Code>.
          </p>
          <Table head={["id", "file written", "aliases", "toolchain"]} rows={languageRows} />
          <ul className="list-disc space-y-1 pl-5">
            <li>
              <strong className="font-medium text-ink">Java</strong>: the file is named after the public
              class (<Code>public class Solution</Code> → <Code>Solution.java</Code>); with no public
              class it is <Code>Main.java</Code>.
            </li>
            <li>
              <strong className="font-medium text-ink">TypeScript</strong>: run directly by Node's
              built-in type stripping — no type checking, type-only syntax is erased.
            </li>
            <li>
              <strong className="font-medium text-ink">Bash</strong>: <Code>bash main.sh</Code>; the{" "}
              <Code>sh</Code>, <Code>shell</Code> and <Code>zsh</Code> fence tags map here.
            </li>
            <li>
              <strong className="font-medium text-ink">Rust</strong>: <Code>rustc -O --edition 2021</Code>,
              single file, standard library only.
            </li>
            <li>
              <strong className="font-medium text-ink">Kotlin</strong>: a top-level <Code>fun main()</Code>;
              compiling takes a few seconds.
            </li>
            <li>
              <strong className="font-medium text-ink">Go</strong>: a single file; a package clause other
              than <Code>main</Code> is rewritten. Standard library only — there is no network to fetch
              modules.
            </li>
            <li>
              <strong className="font-medium text-ink">Python</strong>: numpy, pandas, requests,
              beautifulsoup4, python-dateutil and pytz are installed (network calls fail).
            </li>
            <li>
              <strong className="font-medium text-ink">C / C++</strong>: gcc with <Code>-std=gnu17 -lm</Code>,
              g++ with <Code>-std=gnu++20</Code>, both <Code>-O2 -Wall</Code> (warnings land in{" "}
              <Code>compile_stderr</Code>).
            </li>
          </ul>
        </Section>

        <Section id="limits" title="Limits">
          <Table
            head={["Limit", "Default"]}
            rows={[
              ["code", "64 KiB"],
              ["stdin", "64 KiB"],
              ["timeout_s", "1–30 s, default 10 (compile phase: 20–60 s depending on the language)"],
              ["stdout / stderr", "64 KiB each; truncated is set when cut"],
              ["per sandbox", limits.tone === "ok" && health.status === "ok" && health.health.runner === "docker" ? limits.text : "512 MiB memory · 1 CPU · 128 processes · 64 MiB scratch · no network"],
              ["rate limit", "30 runs per minute per client on the public demo"],
            ]}
          />
          <p>All of these are configurable when you run your own instance.</p>
        </Section>

        <Section id="security" title="Security model">
          <p>
            With the Docker backend, every execution gets its own container that is removed
            afterwards — nothing is shared between two requests. The container has no network, a
            read-only root filesystem with small tmpfs scratch space, memory / CPU / process limits,
            all Linux capabilities dropped, <Code>no-new-privileges</Code>, a non-root user and a hard
            <Code>SIGKILL</Code> deadline backed by a watchdog. The API and the sandbox are separate
            images: the sandbox never contains application code or secrets.
          </p>
          <p>
            What it does <em>not</em> cover: kernel exploits (containers share the host kernel — use
            the Lambda backend or a micro-VM runtime if that is in your threat model), and anything
            that can run code in the API process itself.{" "}
            <a
              className="text-ink underline decoration-paper-line underline-offset-4 hover:decoration-ink"
              href="https://github.com/daviskeene/glimpse/blob/main/docs/security.md"
              target="_blank"
              rel="noopener noreferrer"
            >
              The full security model, control by control.
            </a>
          </p>
        </Section>

        <Section id="self-host" title="Self-hosting">
          <p>The whole stack is one command on any machine with Docker:</p>
          <CodeBlock
            title="shell"
            code={`git clone https://github.com/daviskeene/glimpse && cd glimpse
docker compose up          # builds the sandbox image, serves the API on :8000`}
          />
          <p>
            Set <Code>GLIMPSE_API_KEYS</Code> to require bearer tokens, <Code>GLIMPSE_CORS_ORIGINS</Code> for
            your front-end, and <Code>GLIMPSE_RUNNER=lambda</Code> to use the AWS Lambda backend instead
            of Docker.{" "}
            <a
              className="text-ink underline decoration-paper-line underline-offset-4 hover:decoration-ink"
              href="https://github.com/daviskeene/glimpse#readme"
              target="_blank"
              rel="noopener noreferrer"
            >
              README
            </a>{" "}
            and{" "}
            <a
              className="text-ink underline decoration-paper-line underline-offset-4 hover:decoration-ink"
              href="https://github.com/daviskeene/glimpse/blob/main/docs/deploy.md"
              target="_blank"
              rel="noopener noreferrer"
            >
              deployment guide
            </a>
            .
          </p>
        </Section>
      </div>
    </div>
  );
}
