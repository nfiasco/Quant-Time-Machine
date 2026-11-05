// The story's rolling clock: New York wall-clock moments as plain minute counts, so
// the engine can tween between them. Wall-clock arithmetic only (no time zones), and
// all formatting goes through lib/time.ts.

import {
  formatEtShortDate,
  formatEtTime,
  type EtDateTime,
} from "@/lib/time";

/** Minutes from 1970-01-01 00:00 to a wall-clock moment. */
export function toMinutes(t: EtDateTime): number {
  return Date.UTC(t.year, t.month - 1, t.day, t.hour, t.minute) / 60000;
}

export function fromMinutes(minutes: number): EtDateTime {
  const d = new Date(Math.round(minutes) * 60000);
  return {
    year: d.getUTCFullYear(),
    month: d.getUTCMonth() + 1,
    day: d.getUTCDate(),
    hour: d.getUTCHours(),
    minute: d.getUTCMinutes(),
  };
}

/** For the HUD, for example "Apr 30, 2020 · 6:03 PM ET". */
export function formatReadout(minutes: number): string {
  const t = fromMinutes(minutes);
  return `${formatEtShortDate(t)} · ${formatEtTime(t)}`;
}

/** For the clock face, for example "Apr 30, 2020". */
export function formatDial(minutes: number): string {
  return formatEtShortDate(fromMinutes(minutes));
}
