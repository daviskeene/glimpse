import { useEffect, useState, type ReactNode } from "react";
import { getHealth } from "@/lib/api";
import { HealthContext, type HealthState } from "@/lib/health";

export default function HealthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<HealthState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      getHealth()
        .then((health) => !cancelled && setState({ status: "ok", health }))
        .catch((err: Error) => !cancelled && setState({ status: "unreachable", message: err.message }));
    load();
    const timer = window.setInterval(load, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return <HealthContext.Provider value={state}>{children}</HealthContext.Provider>;
}

