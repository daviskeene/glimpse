import type { ServerTiming } from "./types.js";

/**
 * Parse a `Server-Timing` header (`queue;dur=0, upload;dur=98, ..., total;dur=281`) into
 * phase → milliseconds, keeping the server's order. Returns `null` for a missing or empty header.
 */
export function parseServerTiming(header: string | null | undefined): ServerTiming | null {
  if (!header) return null;
  const timing: ServerTiming = {};
  for (const entry of header.split(",")) {
    const [rawName, ...params] = entry.trim().split(";");
    const name = rawName?.trim();
    if (!name) continue;
    const dur = params.map((p) => p.trim()).find((p) => p.toLowerCase().startsWith("dur="));
    if (!dur) continue;
    const ms = Number(dur.slice(4));
    if (Number.isFinite(ms)) timing[name] = ms;
  }
  return Object.keys(timing).length ? timing : null;
}
