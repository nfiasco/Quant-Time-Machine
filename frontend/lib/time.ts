// Market time helpers. Every moment the app shows is New York wall-clock time,
// labelled "ET", and formatted the same way on the server and in every browser.
// Never format these with the viewer's locale or time zone (toLocaleString() and
// friends): the result would differ per viewer and break hydration.

/** The market clock (NYSE). Knowledge times are always in this zone. */
export const MARKET_TIME_ZONE = "America/New_York";

/** A bare date means 09:30 ET on that date (roadmap §2.2). */
export const DEFAULT_DECISION_TIME = { hour: 9, minute: 30 } as const;

/** A wall-clock moment in New York time. */
export type EtDateTime = {
  year: number;
  month: number; // 1–12
  day: number;
  hour: number; // 0–23
  minute: number;
};

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

const AS_OF_PATTERN = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::\d{2})?)?$/;

const pad = (n: number) => String(n).padStart(2, "0");

/**
 * Parses an `as_of` value, the API's knowledge-time parameter: `YYYY-MM-DD` (which
 * means 09:30 ET) or `YYYY-MM-DDTHH:mm`. Accepts a raw search param, so arrays use
 * their first value. Returns null for anything missing or invalid.
 */
export function parseAsOf(value: string | string[] | undefined): EtDateTime | null {
  const raw = Array.isArray(value) ? value[0] : value;
  const match = raw ? AS_OF_PATTERN.exec(raw.trim()) : null;
  if (!match) return null;

  const [year, month, day] = [match[1], match[2], match[3]].map(Number);
  const hour = match[4] ? Number(match[4]) : DEFAULT_DECISION_TIME.hour;
  const minute = match[5] ? Number(match[5]) : DEFAULT_DECISION_TIME.minute;
  if (month < 1 || month > 12 || hour > 23 || minute > 59) return null;

  // Rejects dates that don't exist, such as February 30.
  const check = new Date(Date.UTC(year, month - 1, day));
  if (check.getUTCMonth() !== month - 1 || check.getUTCDate() !== day) return null;

  return { year, month, day, hour, minute };
}

/** The `as_of` search param for a moment, for example `2020-06-05T09:30`. */
export function toAsOfParam(t: EtDateTime): string {
  return `${t.year}-${pad(t.month)}-${pad(t.day)}T${pad(t.hour)}:${pad(t.minute)}`;
}

/** A calendar date, such as a session, a period end, or a filing date. */
export type EtDate = Pick<EtDateTime, "year" | "month" | "day">;

/** Parses a `YYYY-MM-DD` date from the API. Returns null for anything else. */
export function parseIsoDate(value: string): EtDate | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = parseAsOf(value);
  return parsed ? { year: parsed.year, month: parsed.month, day: parsed.day } : null;
}

/**
 * The New York wall-clock time of an API timestamp, such as `2020-06-05T08:30:00-04:00`.
 * The API writes every timestamp in New York time with its offset, so the first 16
 * characters are the ET wall-clock time (doc/api-v1.md, "Conventions").
 */
export function etDateTimeOf(timestamp: string): EtDateTime | null {
  return parseAsOf(timestamp.slice(0, 16));
}

const FRACTION_PATTERN = /\.(\d{3})(\d+)/;

/**
 * The instant of an API timestamp in milliseconds since the epoch, for comparing and
 * sorting. Keeps fractions finer than a millisecond (the API writes microseconds, such as
 * `23:59:59.999999` for an assumed end of day), so a record never crosses a moment.
 * NaN for a malformed value.
 */
export function instantOf(timestamp: string): number {
  // Date.parse reads ISO 8601 with an offset the same way everywhere, but only to the
  // millisecond: parse that much and add the rest.
  const fraction = FRACTION_PATTERN.exec(timestamp);
  if (!fraction) return Date.parse(timestamp);
  const milliseconds = Date.parse(timestamp.replace(fraction[0], `.${fraction[1]}`));
  return milliseconds + Number(`0.${fraction[2]}`);
}

/**
 * An observation period as people say it: "May 2020" for a monthly series, "Q2 2020"
 * for a quarterly one, "2020" for an annual one, otherwise the date ("Jun 4, 2020").
 * `period` is the API's `YYYY-MM-DD` start of the period.
 */
export function formatPeriod(period: string, frequency: string): string {
  const date = parseIsoDate(period);
  if (!date) return period;
  const kind = frequency.trim().toLowerCase();
  if (kind.startsWith("month")) return `${MONTHS[date.month - 1]} ${date.year}`;
  if (kind.startsWith("quarter")) return `Q${Math.floor((date.month - 1) / 3) + 1} ${date.year}`;
  if (kind.startsWith("annual") || kind.startsWith("year")) return String(date.year);
  return formatEtShortDate(date);
}

/** For example "June 5, 2020". */
export function formatEtDate(t: EtDate): string {
  return `${MONTHS[t.month - 1]} ${t.day}, ${t.year}`;
}

/** For example "9:30 AM ET". */
export function formatEtTime(t: EtDateTime): string {
  const hour12 = t.hour % 12 === 0 ? 12 : t.hour % 12;
  return `${hour12}:${pad(t.minute)} ${t.hour < 12 ? "AM" : "PM"} ET`;
}

/** For example "June 5, 2020, 9:30 AM ET". */
export function formatEtDateTime(t: EtDateTime): string {
  return `${formatEtDate(t)}, ${formatEtTime(t)}`;
}

/** Compact date for tight spaces, for example "Jun 5, 2020". */
export function formatEtShortDate(t: EtDate): string {
  return `${MONTHS[t.month - 1].slice(0, 3)} ${t.day}, ${t.year}`;
}

const ET_PARTS = new Intl.DateTimeFormat("en-US", {
  timeZone: MARKET_TIME_ZONE,
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "numeric",
  hourCycle: "h23",
});

/**
 * The New York wall-clock time of an instant, such as "now". Call it only in the
 * browser after hydration (an effect or event handler): during rendering, the server
 * and the browser would read different clocks.
 */
export function toEtDateTime(instant: Date): EtDateTime {
  const parts: Record<string, number> = {};
  for (const part of ET_PARTS.formatToParts(instant)) {
    if (part.type !== "literal") parts[part.type] = Number(part.value);
  }
  return {
    year: parts.year,
    month: parts.month,
    day: parts.day,
    hour: parts.hour,
    minute: parts.minute,
  };
}
