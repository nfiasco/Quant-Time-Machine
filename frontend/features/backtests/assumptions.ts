import { describeDelisting } from "@/features/backtests/describe-delisting";
import { describeDecision } from "@/features/backtests/describe-schedule";
import type { ExperimentSpec } from "@/features/backtests/types";
import { universeLabel } from "@/features/backtests/universes";
import { formatBps } from "@/lib/format";

// The assumptions behind a run's numbers, shown up front on its results page (NFR-3,
// GUIDELINES.md §1): the ones its spec chose, and the ones every run makes.

export type Assumption = { term: string; detail: string };

/** What the spec chose: decisions, fills, costs, delistings, the benchmark, the universe. */
export function specAssumptions(spec: ExperimentSpec): Assumption[] {
  const fill =
    spec.schedule.fill === "same_day_close"
      ? "At the decision day's close, 4:00 PM ET or 1:00 PM on an early-close day, so a decision never sees the bar it trades at"
      : "At the next session's open, the day after each decision";
  return [
    {
      term: "Decisions",
      detail: `Monthly, on the ${describeDecision(spec.schedule.decision)}, using only what was public by then`,
    },
    { term: "Fills", detail: fill },
    {
      term: "Costs",
      detail: `${formatBps(spec.costs.bps_per_trade)} of the value traded, on every trade`,
    },
    {
      term: "Delistings",
      detail: `${describeDelisting(spec.delisting)}, for a holding that stops trading`,
    },
    {
      term: "Benchmark",
      detail: `${spec.benchmark}, its total return between the same prices`,
    },
    {
      term: "Universe",
      detail: `${universeLabel(spec.universe.id)}, as its membership was at each decision`,
    },
  ];
}

/**
 * What every run assumes, which no spec changes (doc/reference/metrics.md and
 * portfolio.md, "Known limitations"). Free shorting matters only to a long-short spec.
 */
export function fixedAssumptions(spec: ExperimentSpec): string[] {
  return [
    "Cash earns nothing.",
    "The risk-free rate is the 3-month Treasury bill rate (TB3MS), as last published by each decision.",
    "Each period counts as a month, so volatility and the Sharpe ratio are annualized by √12.",
    "Costs are one flat rate on everything traded: no spread, price impact, or minimum commission.",
    "Drawdowns are seen only at each month's fill, so a fall within a month doesn't show.",
    ...(spec.portfolio.long_only
      ? []
      : ["Shorting is free and always possible: no borrow fee, margin, or recall."]),
  ];
}
