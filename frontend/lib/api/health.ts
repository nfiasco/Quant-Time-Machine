import { cache } from "react";

import { apiFetch } from "@/lib/api/client";

export type ApiHealth =
  | { status: "online" }
  | { status: "offline"; reason: string };

/**
 * Checks `GET /health` on the backend. Never throws: an unreachable or unhealthy API
 * comes back as `offline` with a short reason, so pages can show it as a status.
 * Call it from the server; the backend doesn't allow browser (CORS) requests yet.
 * Memoized per request, so several components can ask without repeating the call.
 */
export const getApiHealth = cache(async (): Promise<ApiHealth> => {
  try {
    const body = await apiFetch<{ status?: string }>("/health", {
      cache: "no-store",
      timeoutMs: 2_000,
    });
    return body.status === "ok"
      ? { status: "online" }
      : { status: "offline", reason: "unexpected response from /health" };
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "TimeoutError";
    return { status: "offline", reason: timedOut ? "timed out" : "not reachable" };
  }
});
