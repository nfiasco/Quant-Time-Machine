import type { EquityPoint } from "@/lib/api/types";

/**
 * The equity curve of doc/reference/metrics.md's worked example: three made-up stocks over
 * four months of 2021, against a made-up SPY. The backend's
 * `test_a_hand_checked_runs_metrics_match_the_worked_example` checks every point, and
 * metrics.md works the run's maximum drawdown by hand: −0.001999, after February.
 */
export const workedCurve = [
  { at: { session: "2021-01-04", price: "close" }, value: 1.0, benchmark: 1.0 },
  { at: { session: "2021-02-01", price: "close" }, value: 0.999, benchmark: 1.02 },
  { at: { session: "2021-03-01", price: "close" }, value: 0.998001, benchmark: 1.0098 },
  { at: { session: "2021-04-01", price: "close" }, value: 1.03058, benchmark: 1.040094 },
  { at: { session: "2021-04-30", price: "close" }, value: 1.132102, benchmark: 1.050495 },
] satisfies EquityPoint[];

/** The worked example's maximum drawdown, as metrics.md works it. */
export const workedMaxDrawdown = -0.001999;
