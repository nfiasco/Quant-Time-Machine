// The Time Machine's URL and form rules, in one place. The URL holds the whole view
// (`as_of`, `tickers`, `series`, named as the API names them), so a link reproduces it.
// Pure functions: the page parses the URL with them, the form validates with them, and
// params.test.ts checks them.

import { demoMoment } from "@/features/time-machine/example-moment";
import type { ApiFailure } from "@/lib/api/errors";
import type { SnapshotParams } from "@/lib/api/snapshot";
import { DEFAULT_DECISION_TIME, parseAsOf, toAsOfParam, type EtDateTime } from "@/lib/time";

/** The most companies, and the most series, one snapshot can list (doc/api-v1.md). */
export const MAX_ENTRIES = 10;

/** Letters and digits, with "." or "-" for a share class (BRK.B, BF-B). */
export const TICKER_PATTERN = /^[A-Z0-9][A-Z0-9.-]{0,9}$/;

/** FRED and ALFRED series IDs, such as UNRATE. */
export const SERIES_PATTERN = /^[A-Z0-9][A-Z0-9_]{0,29}$/;

const pad = (n: number) => String(n).padStart(2, "0");

/** What a blank time field means: 09:30, the market open (roadmap §2.2). */
export const DEFAULT_TIME = `${pad(DEFAULT_DECISION_TIME.hour)}:${pad(DEFAULT_DECISION_TIME.minute)}`;

const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/;
const OFFSET_PATTERN = /T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})$/i;

/** The URL's parameters, which are also the API's field names in a 422. */
export type ParamName = "as_of" | "tickers" | "series";

/** A message per parameter, shown under the matching form field. */
export type FieldErrors = Partial<Record<ParamName, string>>;

/** What the form holds: strings for the date and time inputs, lists for the pickers. */
export type ExplorerValues = {
  /** `YYYY-MM-DD`, or "" when no date is chosen. */
  date: string;
  /** `HH:mm`; "" means 09:30 ET. */
  time: string;
  tickers: string[];
  series: string[];
};

/** A valid request: a moment, plus at least one company or series. */
export type ExplorerQuery = { moment: EtDateTime; tickers: string[]; series: string[] };

export type ExplorerUrlState =
  | "blank" // nothing chosen yet
  | "moment-only" // a valid moment but no companies or series (older links send only as_of)
  | "ready" // a valid query
  | "invalid"; // something in the URL can't be used: see `issues`

export type ExplorerUrl = {
  /** What the form starts from. */
  values: ExplorerValues;
  /** Problems with the URL, by parameter. */
  issues: FieldErrors;
  /** The knowledge time, when `as_of` is valid. */
  moment: EtDateTime | null;
  /** Set only when the state is "ready". */
  query: ExplorerQuery | null;
  state: ExplorerUrlState;
};

type SearchParams = Record<string, string | string[] | undefined>;

/** The §2.3 example: June 5, 2020, at 9:30 AM ET, as the snapshot's golden test asks it. */
export const demoQuery: ExplorerQuery = {
  moment: demoMoment,
  tickers: ["AAPL", "TSLA"],
  series: ["UNRATE", "FEDFUNDS"],
};

/**
 * A selection that answers at any moment from 1980 on, for links that pick only a moment
 * (the dashboard's quick start). TSLA isn't in it: before its 2010 listing the API doesn't
 * know the ticker and fails the whole request.
 */
export const starterSelection = { tickers: ["AAPL"], series: ["UNRATE", "FEDFUNDS"] } as const;

/**
 * The `as_of` the pickers' catalogs are read at: 09:30 ET on the moment's date. Universe
 * membership and tickers change only from an effective date's start, so one time a day
 * gives the same list, and 09:30 always exists, unlike times in the daylight-saving gap.
 */
export function catalogAsOf(moment: Pick<EtDateTime, "year" | "month" | "day">): string {
  return toAsOfParam({ year: moment.year, month: moment.month, day: moment.day, ...DEFAULT_DECISION_TIME });
}

/** A full query for a moment: the §2.3 selection on its own moment, else the starter. */
export function suggestedQuery(moment: EtDateTime): ExplorerQuery {
  if (toAsOfParam(moment) === toAsOfParam(demoMoment)) return demoQuery;
  return {
    moment,
    tickers: [...starterSelection.tickers],
    series: [...starterSelection.series],
  };
}

/**
 * Reads a list parameter the way the API does: comma-separated, trimmed, any case, blanks
 * dropped, repeats counted once, order kept. Repeated keys are joined, because the API
 * would read only the last one.
 */
export function parseEntries(raw: string | string[] | undefined): string[] {
  const joined = Array.isArray(raw) ? raw.join(",") : (raw ?? "");
  const entries: string[] = [];
  for (const part of joined.split(",")) {
    const entry = part.trim().toUpperCase();
    if (entry && !entries.includes(entry)) entries.push(entry);
  }
  return entries;
}

/** Parses the page's search params into form values, problems, and a query to run. */
export function parseExplorerUrl(searchParams: SearchParams): ExplorerUrl {
  const asOfParam = searchParams.as_of;
  const rawAsOf = (Array.isArray(asOfParam) ? asOfParam[0] : asOfParam)?.trim() ?? "";
  const tickers = parseEntries(searchParams.tickers);
  const series = parseEntries(searchParams.series);
  const moment = rawAsOf ? parseAsOf(rawAsOf) : null;
  const values: ExplorerValues = {
    date: moment ? toAsOfParam(moment).slice(0, 10) : "",
    time: moment ? toAsOfParam(moment).slice(11) : DEFAULT_TIME,
    tickers,
    series,
  };

  if (!rawAsOf && tickers.length === 0 && series.length === 0) {
    return { values, issues: {}, moment: null, query: null, state: "blank" };
  }

  const issues: FieldErrors = {};
  if (!rawAsOf) issues.as_of = "Pick a date for the knowledge time.";
  else if (!moment) issues.as_of = asOfIssue(rawAsOf);
  const tickersIssue = listIssue("tickers", tickers);
  if (tickersIssue) issues.tickers = tickersIssue;
  const seriesIssue = listIssue("series", series);
  if (seriesIssue) issues.series = seriesIssue;

  if (Object.keys(issues).length > 0) {
    return { values, issues, moment, query: null, state: "invalid" };
  }
  if (!moment || (tickers.length === 0 && series.length === 0)) {
    return { values, issues, moment, query: null, state: "moment-only" };
  }
  return { values, issues, moment, query: { moment, tickers, series }, state: "ready" };
}

/** Checks the form's values before they go into the URL. */
export function validateValues(values: ExplorerValues): {
  errors: FieldErrors;
  query: ExplorerQuery | null;
} {
  const errors: FieldErrors = {};
  const time = values.time.trim() || DEFAULT_TIME;
  const moment = values.date ? parseAsOf(`${values.date}T${time.slice(0, 5)}`) : null;

  if (!values.date) errors.as_of = "Pick a date.";
  else if (!TIME_PATTERN.test(time)) errors.as_of = "Use a time such as 09:30.";
  else if (!moment) errors.as_of = "That date doesn't exist.";

  const tickersIssue = listIssue("tickers", values.tickers);
  if (tickersIssue) errors.tickers = tickersIssue;
  const seriesIssue = listIssue("series", values.series);
  if (seriesIssue) errors.series = seriesIssue;
  // The API names `tickers` when both lists are empty, so the message sits there too.
  if (!tickersIssue && !seriesIssue && values.tickers.length + values.series.length === 0) {
    errors.tickers = "Choose at least one company or series.";
  }

  if (Object.keys(errors).length > 0 || !moment) return { errors, query: null };
  return { errors, query: { moment, tickers: values.tickers, series: values.series } };
}

/**
 * A string that's equal for equal values, so the form can tell when the URL now holds
 * something else (after back or forward) and reset itself.
 */
export function valuesKey(values: ExplorerValues): string {
  const time = (values.time.trim() || DEFAULT_TIME).slice(0, 5);
  return `${values.date}T${time}|${values.tickers.join(",")}|${values.series.join(",")}`;
}

/** The values a query puts in the form. */
export function valuesOf(query: ExplorerQuery): ExplorerValues {
  const asOf = toAsOfParam(query.moment);
  return {
    date: asOf.slice(0, 10),
    time: asOf.slice(11),
    tickers: [...query.tickers],
    series: [...query.series],
  };
}

/**
 * Maps an API failure onto form fields: a 422's details by parameter, and an unknown
 * ticker or series to its list. Other failures belong to no field.
 */
export function fieldErrorsFromFailure(failure: ApiFailure): FieldErrors {
  if (failure.kind !== "response") return {};
  if (failure.code === "unknown_ticker") return { tickers: failure.message };
  if (failure.code === "unknown_series") return { series: failure.message };
  if (failure.code !== "invalid_request") return {};

  const errors: FieldErrors = {};
  for (const { field, message } of failure.details) {
    // A missing as_of is reported twice; keep the first message per field.
    if (isParamName(field) && !errors[field]) errors[field] = message;
  }
  return errors;
}

/**
 * The link for a query, with commas and colons left readable:
 * `/time-machine?as_of=2020-06-05T09:30&tickers=AAPL,TSLA&series=UNRATE,FEDFUNDS`.
 * Empty lists are left out, so a moment alone gives `/time-machine?as_of=…`.
 */
export function explorerHref({ moment, tickers, series }: ExplorerQuery): `/time-machine?${string}` {
  const params = new URLSearchParams({ as_of: toAsOfParam(moment) });
  if (tickers.length > 0) params.set("tickers", tickers.join(","));
  if (series.length > 0) params.set("series", series.join(","));
  return `/time-machine?${params.toString().replaceAll("%2C", ",").replaceAll("%3A", ":")}`;
}

/** The snapshot request for a query. */
export function snapshotParamsOf({ moment, tickers, series }: ExplorerQuery): SnapshotParams {
  return { asOf: toAsOfParam(moment), tickers, series };
}

function isParamName(field: string): field is ParamName {
  return field === "as_of" || field === "tickers" || field === "series";
}

function asOfIssue(raw: string): string {
  if (OFFSET_PATTERN.test(raw)) {
    return `“${raw}” has a time zone. The Time Machine uses New York time without an offset, such as 2020-06-05T09:30.`;
  }
  return `“${raw}” isn't a knowledge time. Use a date such as 2020-06-05 (09:30 ET that day) or a New York time such as 2020-06-05T09:30.`;
}

function listIssue(name: "tickers" | "series", entries: string[]): string | undefined {
  const isTickers = name === "tickers";
  const invalid = entries.filter((entry) => !(isTickers ? TICKER_PATTERN : SERIES_PATTERN).test(entry));
  if (invalid.length > 0) {
    const subject = quoteList(invalid);
    const verb = invalid.length === 1 ? "isn't" : "aren't";
    return isTickers
      ? `${subject} ${verb} ${invalid.length === 1 ? "a ticker" : "tickers"}: use letters and digits, with “.” or “-” for a share class, such as BRK.B.`
      : `${subject} ${verb} ${invalid.length === 1 ? "a series ID" : "series IDs"}: use letters, digits, and “_”, such as UNRATE.`;
  }
  if (entries.length > MAX_ENTRIES) {
    return `Choose at most ${MAX_ENTRIES} ${isTickers ? "companies" : "series"} (there are ${entries.length}).`;
  }
  return undefined;
}

function quoteList(items: string[]): string {
  const quoted = items.map((item) => `“${item}”`);
  return quoted.length <= 2
    ? quoted.join(" and ")
    : `${quoted.slice(0, -1).join(", ")}, and ${quoted.at(-1)}`;
}
