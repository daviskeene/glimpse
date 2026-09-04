import type { ReactNode } from "react";
import { useHealth } from "@glimpse-run/react";
import { HealthContext, type HealthState } from "@/lib/health";

/** Polls /health through the shared client every 30 s and exposes it to the header and docs. */
export default function HealthProvider({ children }: { children: ReactNode }) {
  const { health, error } = useHealth({ intervalMs: 30_000 });
  const state: HealthState = error
    ? { status: "unreachable", message: error.message }
    : health
      ? { status: "ok", health }
      : { status: "loading" };
  return <HealthContext.Provider value={state}>{children}</HealthContext.Provider>;
}
