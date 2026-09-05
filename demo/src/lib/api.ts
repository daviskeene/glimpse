/**
 * The demo's Glimpse client. The public instance's URL is baked in at build time
 * (`VITE_GLIMPSE_API_URL`, see .env.production); everything else comes from the packages.
 */
import { createClient, type Health, type LanguageInfo } from "@glimpse-run/client";

export type { ExecuteResponse, Execution, Health, LanguageInfo, ServerTiming } from "@glimpse-run/client";
export {
  GlimpseApiError,
  GlimpseError,
  GlimpseNetworkError,
  GlimpseTimeoutError,
  isSuccess,
} from "@glimpse-run/client";

const raw = import.meta.env.VITE_GLIMPSE_API_URL as string | undefined;
export const API_URL = (raw && raw.trim() ? raw.trim() : "http://localhost:8000").replace(/\/+$/, "");

/** One client for the whole app; the hooks reach it through `<GlimpseProvider client={client}>`. */
export const client = createClient({ baseUrl: API_URL });

export const listLanguages = (): Promise<LanguageInfo[]> => client.languages();
export const getHealth = (): Promise<Health> => client.health();
