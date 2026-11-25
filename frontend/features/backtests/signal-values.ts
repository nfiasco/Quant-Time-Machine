import type { SignalSpec } from "@/features/backtests/types";
import { formatNumber, formatPercent, formatPoints } from "@/lib/format";

// A signal's value as people read it, by its kind (doc/reference/signals.md). The engine's
// values are fractions, 0.01 for 1%, except an absolute macro change, which is in its
// series' units. A kind this page doesn't know yet still shows, as a plain number.

/** "+13.5%" for momentum or revenue growth, "−8.39 pts" for an acceleration, "—" for none. */
export function formatSignalValue(
  value: number | null | undefined,
  signal: SignalSpec | undefined,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  switch (signal?.type) {
    case "momentum":
    case "revenue_growth":
      return formatPercent(value, { signed: true });
    case "revenue_growth_acceleration":
      return formatPoints(value);
    case "macro_change":
      return signal.change === "relative"
        ? formatPercent(value, { signed: true })
        : signed(formatNumber(value), value);
    default:
      return signed(formatNumber(value), value);
  }
}

/** The unit a column of this signal's values is in, for its header: "%", "pts", or none. */
export function signalUnit(signal: SignalSpec | undefined): string | null {
  switch (signal?.type) {
    case "momentum":
    case "revenue_growth":
      return "%";
    case "revenue_growth_acceleration":
      return "pts";
    case "macro_change":
      return signal.change === "relative" ? "%" : `${signal.series} units`;
    default:
      return null;
  }
}

function signed(text: string, value: number): string {
  if (text === "0") return text;
  return value < 0 ? `−${text.replace("-", "")}` : `+${text}`;
}
