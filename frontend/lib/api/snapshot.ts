import { apiFetch } from "@/lib/api/client";
import type { Snapshot, V1Response } from "@/lib/api/types";

export type SnapshotParams = {
  /** The knowledge time, in a form the API's `as_of` accepts, such as `2020-06-05T09:30`. */
  asOf: string;
  tickers: readonly string[];
  series: readonly string[];
};

/**
 * The path for `GET /v1/snapshot`. Each list goes as one comma-separated value, because
 * the API reads only the last of repeated keys. Empty lists are left out. Commas and
 * colons stay readable, since they're allowed in a query string.
 */
export function snapshotPath({
  asOf,
  tickers,
  series,
}: SnapshotParams): `/v1/snapshot?${string}` {
  const query = new URLSearchParams({ as_of: asOf });
  if (tickers.length > 0) query.set("tickers", tickers.join(","));
  if (series.length > 0) query.set("series", series.join(","));
  const readable = query.toString().replaceAll("%2C", ",").replaceAll("%3A", ":");
  return `/v1/snapshot?${readable}`;
}

/**
 * What was known at a moment, and what wasn't yet, for chosen companies and series (S8.3).
 * Call it from a Server Component: the API's CORS lets browsers in only from
 * localhost:3000 and the production site. Throws like `apiFetch`; wrap it in `settle`
 * (lib/api/errors.ts) to render a failure instead.
 */
export function getSnapshot(params: SnapshotParams): Promise<V1Response<Snapshot>> {
  return apiFetch<V1Response<Snapshot>>(snapshotPath(params), { cache: "no-store" });
}
