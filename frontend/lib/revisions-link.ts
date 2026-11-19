import { toAsOfParam, type EtDateTime } from "@/lib/time";

export type RevisionsLinkParams = {
  /** A series ID, such as `UNRATE`. */
  series: string;
  /** The observation's date as the API writes it: `1990-01-01` is January 1990. */
  period: string;
  /** The Time Machine's moment, so the viewer highlights the value visible then. */
  asOf?: EtDateTime;
};

/**
 * The link to the revision viewer for one observation, with colons left readable:
 * `/revisions?series=UNRATE&period=1990-01-01&as_of=2020-06-05T09:30`. It lives in lib/
 * because the Time Machine links to the viewer and features don't import each other.
 */
export function revisionsHref({ series, period, asOf }: RevisionsLinkParams): `/revisions?${string}` {
  const params = new URLSearchParams({ series, period });
  if (asOf) params.set("as_of", toAsOfParam(asOf));
  return `/revisions?${params.toString().replaceAll("%3A", ":")}`;
}