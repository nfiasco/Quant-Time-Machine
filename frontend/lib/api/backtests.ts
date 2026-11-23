import { apiFetch } from "@/lib/api/client";
import type { GetResponse, PostBody, PostResponse } from "@/lib/api/types";

// The backtest endpoints (S8.4). Call them from the server, like every v1 endpoint: from a
// Server Component, or the builder's Server Action. Nothing here goes in Next's data cache,
// since a run changes while it goes (api-v1.md, "Backtests").

/** A run ID: all 64 hex digits of a SHA-256, as the API writes them (backend `RUN_ID`). */
const RUN_ID = /^[0-9a-f]{64}$/;

/** True for a string shaped like a run ID. Check one before putting it in a path or a link. */
export function isRunId(value: unknown): value is string {
  return typeof value === "string" && RUN_ID.test(value);
}

/** The API path of a run, such as `/v1/backtests/9dfe…b30f`. */
export function backtestPath(runId: string): `/v1/backtests/${string}` {
  return `/v1/backtests/${encodeURIComponent(runId)}`;
}

/**
 * Submits an experiment spec (`POST /v1/backtests`). The API answers at once with the run's
 * ID, 202 when the run is queued or already in progress and 200 when it's already saved;
 * either way, read it with `getBacktestRun`. Throws like `apiFetch`: a 422 names each
 * invalid field by its path in the spec, and a 503 means the queue is full or the server
 * can't save runs.
 */
export function submitBacktest(
  spec: PostBody<"/v1/backtests">,
): Promise<PostResponse<"/v1/backtests">> {
  return apiFetch<PostResponse<"/v1/backtests">>("/v1/backtests", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
    cache: "no-store",
  });
}

/**
 * A run (`GET /v1/backtests/{run_id}`): its status, its progress while it runs, and once it
 * has succeeded, its metrics, periods, equity curve, and warnings. A 404 means no run has
 * that ID.
 */
export function getBacktestRun(runId: string): Promise<GetResponse<"/v1/backtests/{run_id}">> {
  return apiFetch<GetResponse<"/v1/backtests/{run_id}">>(backtestPath(runId), {
    cache: "no-store",
  });
}
