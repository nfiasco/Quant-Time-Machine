import { apiFetch } from "@/lib/api/client";
import type { MacroObservation, V1Response } from "@/lib/api/types";

/**
 * An `as_of` after every vintage our data holds, to ask for all of an observation's
 * versions. The revision viewer does this on purpose: it exists to show what was published
 * after the Time Machine's moment, like the snapshot's "not yet known" half. The API
 * answers from the newest data version whatever `as_of` is, so a later date adds nothing.
 */
export const ALL_VINTAGES_AS_OF = "2100-01-01";

export type RevisionsParams = {
  /** A series ID in the catalog, such as `UNRATE`. */
  series: string;
  /** The observation's date as the API writes it: `1990-01-01` is January 1990. */
  period: string;
  /** The knowledge time, in a form the API's `as_of` accepts, such as `2020-06-05T09:30`. */
  asOf: string;
};

/** The path for `GET /v1/macro/{series_id}/revisions`; colons stay readable. */
export function revisionsPath({
  series,
  period,
  asOf,
}: RevisionsParams): `/v1/macro/${string}/revisions?${string}` {
  const query = new URLSearchParams({ as_of: asOf, period }).toString().replaceAll("%3A", ":");
  return `/v1/macro/${encodeURIComponent(series)}/revisions?${query}`;
}

/**
 * Every version of one observation published by `asOf`, oldest first (S4.5). `data` is `[]`
 * with a `reason` when nothing had been published. Call it from a Server Component; throws
 * like `apiFetch`, so wrap it in `settle` (lib/api/errors.ts) to render a failure instead.
 */
export function getRevisions(params: RevisionsParams): Promise<V1Response<MacroObservation[]>> {
  return apiFetch<V1Response<MacroObservation[]>>(revisionsPath(params), { cache: "no-store" });
}