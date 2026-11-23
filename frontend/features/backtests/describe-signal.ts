import type { SignalSpec } from "@/features/backtests/types";

/**
 * A spec's signal in plain language, for the spec summary. Momentum without its
 * parameters is the spec's default, 12-1 (backend/app/backtest/spec.py). Each signal's
 * formula is in doc/reference/signals.md. A number the builder's form can't read yet, such
 * as a blank field's, shows as "?".
 */
export function describeSignal(signal: SignalSpec): string {
  switch (signal.type) {
    case "momentum":
      return `Momentum, ${count(signal.lookback_months ?? 12)}-month lookback, skipping the last ${count(signal.skip_months ?? 1)}`;
    case "revenue_growth":
      return "Revenue growth (year over year, quarterly)";
    case "revenue_growth_acceleration":
      return "Revenue growth acceleration (year over year, quarterly)";
    case "macro_change":
      return `${signal.series || "?"}'s ${signal.change} change over its last ${count(signal.releases)} ${signal.releases === 1 ? "release" : "releases"}`;
  }
}

function count(value: number): string {
  return Number.isFinite(value) ? String(value) : "?";
}
