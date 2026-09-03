import { createContext, useContext } from "react";
import type { Health } from "./api";

export type HealthState =
  | { status: "loading" }
  | { status: "ok"; health: Health }
  | { status: "unreachable"; message: string };

export const HealthContext = createContext<HealthState>({ status: "loading" });

export const useHealth = () => useContext(HealthContext);

/** One-line description of the isolation the backend currently provides. */
export function describeLimits(state: HealthState): { text: string; tone: "ok" | "warn" | "off" } {
  if (state.status !== "ok") return { text: "limits unknown", tone: "off" };
  const { runner, details } = state.health;
  if (runner === "docker") {
    const l = details.limits ?? {};
    const parts = [
      l.memory_mb ? `${l.memory_mb} MiB` : null,
      l.cpus ? `${l.cpus} cpu` : null,
      l.pids ? `${l.pids} pids` : null,
      l.network === "none" ? "no network" : null,
    ].filter(Boolean);
    return { text: parts.join(" · "), tone: "ok" };
  }
  if (runner === "lambda") return { text: `aws lambda · ${details.function ?? "function"}`, tone: "ok" };
  if (runner === "unsafe-local") return { text: "unsafe-local · no isolation", tone: "warn" };
  return { text: runner, tone: "ok" };
}
