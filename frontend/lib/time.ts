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

/** For example "June 5, 2020". */
export function formatEtDate(t: EtDateTime): string {
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
