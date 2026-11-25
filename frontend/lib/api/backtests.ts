import { apiFetch } from "@/lib/api/client";
import type { GetResponse, PostBody, PostResponse } from "@/lib/api/types";

// The backtest endpoints (S8.4, S9.6). Call them from the server, like every v1 endpoint:
// from a Server Component, or the builder's Server Action. Nothing here goes in Next's data
// cache, since a run changes while it goes (api-v1.md, "Backtests"), and a saved run can
// gain a file its layout didn't keep, such as members.json, at the same address.

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

/** The parts of a run that list an entry for each decision, which `decision` narrows. */
export type RunPart = "audit" | "holdings" | "trades" | "members";

/**
 * The API path of one part of a run, all of it or one decision's, such as
 * `/v1/backtests/9dfe…b30f/holdings?decision=2020-06-01`.
 */
export function backtestPartPath(
  runId: string,
  part: RunPart | "coverage",
  decision?: string,
): `/v1/backtests/${string}` {
  const path = `${backtestPath(runId)}/${part}` as const;
  return decision ? `${path}?${new URLSearchParams({ decision })}` : path;
}

/**
 * What each view the run opened at one decision read, and when the newest of it became
 * known (`GET /v1/backtests/{run_id}/audit?decision=`): two views, or three at the run's
 * last decision. `views` is null until the run has succeeded.
 */
export function getBacktestAudit(
  runId: string,
  decision: string,
): Promise<GetResponse<"/v1/backtests/{run_id}/audit">> {
  return apiFetch<GetResponse<"/v1/backtests/{run_id}/audit">>(
    backtestPartPath(runId, "audit", decision),
    { cache: "no-store" },
  );
}

/** What one decision held from its fill (`GET /v1/backtests/{run_id}/holdings?decision=`). */
export function getBacktestHoldings(
  runId: string,
  decision: string,
): Promise<GetResponse<"/v1/backtests/{run_id}/holdings">> {
  return apiFetch<GetResponse<"/v1/backtests/{run_id}/holdings">>(
    backtestPartPath(runId, "holdings", decision),
    { cache: "no-store" },
  );
}

/** One decision's trades at its fill (`GET /v1/backtests/{run_id}/trades?decision=`). */
export function getBacktestTrades(
  runId: string,
  decision: string,
): Promise<GetResponse<"/v1/backtests/{run_id}/trades">> {
  return apiFetch<GetResponse<"/v1/backtests/{run_id}/trades">>(
    backtestPartPath(runId, "trades", decision),
    { cache: "no-store" },
  );
}

/**
 * Every member of the universe at one decision, its signals, and whether the run held it,
 * or why not (`GET /v1/backtests/{run_id}/members?decision=`, S9.6). `members` is null
 * for a run saved before record version 3.
 */
export function getBacktestMembers(
  runId: string,
  decision: string,
): Promise<GetResponse<"/v1/backtests/{run_id}/members">> {
  return apiFetch<GetResponse<"/v1/backtests/{run_id}/members">>(
    backtestPartPath(runId, "members", decision),
    { cache: "no-store" },
  );
}

/**
 * What data the run's decisions lacked, by security and year, and the holdings it valued
 * at their last close (`GET /v1/backtests/{run_id}/coverage`, S6.7). `coverage` is null for
 * a run saved before engine 1.1.0.
 */
export function getBacktestCoverage(
  runId: string,
): Promise<GetResponse<"/v1/backtests/{run_id}/coverage">> {
  return apiFetch<GetResponse<"/v1/backtests/{run_id}/coverage">>(
    backtestPartPath(runId, "coverage"),
    { cache: "no-store" },
  );
}
