import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";
import { API_URL } from "@/lib/api";
import { useHealth } from "@/lib/health";

function HealthChip() {
  const state = useHealth();
  const dot =
    state.status === "ok"
      ? state.health.runner === "unsafe-local"
        ? "bg-coral"
        : "bg-mint"
      : state.status === "loading"
        ? "bg-mist animate-pulse"
        : "bg-coral";
  const label =
    state.status === "ok"
      ? `${state.health.runner}${
          state.health.details.pool_ready !== undefined
            ? ` · ${state.health.details.pool_ready} warm`
            : ""
        }`
      : state.status === "loading"
        ? "checking API"
        : "API unreachable";
  return (
    <span
      title={`${API_URL}/health`}
      className="hidden items-center gap-2 rounded-full border border-paper-line bg-paper-deep/60 px-3 py-1 font-mono text-[11px] text-ink-soft sm:inline-flex"
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", dot)} aria-hidden />
      {label}
    </span>
  );
}

const link = ({ isActive }: { isActive: boolean }) =>
  cn(
    "rounded-md px-2.5 py-1.5 text-sm transition-colors hover:text-ink",
    isActive ? "text-ink font-medium" : "text-ink-soft",
  );

export default function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-paper-line/70 bg-paper/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
        <NavLink to="/" className="group flex items-center gap-2.5">
          <span
            aria-hidden
            className="relative block h-5 w-5 rounded-[5px] bg-petrol shadow-[inset_0_0_0_1.5px_#245459]"
          >
            <span className="absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-amber transition-transform group-hover:scale-125" />
          </span>
          <span className="font-display text-[19px] font-semibold tracking-tight text-ink">Glimpse</span>
        </NavLink>
        <nav className="flex items-center gap-1 sm:gap-3">
          <NavLink to="/" end className={link}>
            Playground
          </NavLink>
          <NavLink to="/docs" className={link}>
            Docs
          </NavLink>
          <a
            href="https://github.com/daviskeene/glimpse"
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md px-2.5 py-1.5 text-sm text-ink-soft transition-colors hover:text-ink"
          >
            GitHub
          </a>
          <HealthChip />
        </nav>
      </div>
    </header>
  );
}
