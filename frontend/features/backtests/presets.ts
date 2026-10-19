import type { ExperimentSpec } from "@/features/backtests/types";

export type Preset = {
  id: string;
  /** The research question, in plain English. */
  question: string;
  spec: ExperimentSpec;
};

/** The project's canonical example (README, doc/roadmap.md §3.4): the CISC 498 demo backtest. */
export const canonicalPreset: Preset = {
  id: "canonical",
  question:
    "Using only information available at the beginning of each month, test whether companies with improving revenue growth and positive momentum outperformed the market from 2010 to 2025.",
  spec: {
    spec_version: 1,
    name: "Improving revenue growth + positive momentum",
    universe: { type: "point_in_time_list", id: "starter_large_caps" },
    period: { start: "2010-01-01", end: "2025-12-31" },
    schedule: {
      rebalance: "monthly",
      decision: "first_trading_day 09:30 America/New_York",
      fill: "same_day_close",
    },
    signals: {
      rev_accel: { type: "revenue_growth_acceleration", basis: "yoy_quarterly" },
      mom_12_1: { type: "momentum", lookback_months: 12, skip_months: 1 },
    },
    filters: [
      { signal: "rev_accel", op: ">", value: 0 },
      { signal: "mom_12_1", op: ">", value: 0 },
    ],
    portfolio: { weighting: "equal", long_only: true },
    benchmark: "SPY",
    costs: { bps_per_trade: 10 },
  },
};

const presets: readonly Preset[] = [canonicalPreset];

/** Looks up a preset by the `preset` search param. */
export function findPreset(id: string | string[] | undefined): Preset | undefined {
  const value = Array.isArray(id) ? id[0] : id;
  return presets.find((preset) => preset.id === value);
}
