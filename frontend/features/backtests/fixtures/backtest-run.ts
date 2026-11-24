import { canonicalPreset } from "@/features/backtests/presets";
import type { GetResponse } from "@/lib/api/types";

/**
 * GET /v1/backtests/9dfe…b30f, as doc/reference/api-v1.md documents it: the canonical spec
 * from 2020 to 2022, run on data version 20261111T030742Z, with one of its 36 periods, two
 * of its equity points, and one of its warnings. The documented example leaves the spec
 * out, so it's the canonical one for that period, with the defaults a run writes out.
 * `satisfies` makes `next build` fail if it no longer matches the route's response type.
 */
export const succeededRun = {
  run_id: "9dfedcfa918368dcbd3d3af6d83abe4496f4ea6ed475303da691b5b1dcb2b30f",
  status: "succeeded",
  progress: null,
  submitted_at: "2026-11-15T21:52:39-05:00",
  started_at: "2026-11-15T21:52:39-05:00",
  finished_at: "2026-11-15T21:53:15-05:00",
  error: null,
  spec: {
    ...canonicalPreset.spec,
    period: { start: "2020-01-01", end: "2022-12-31" },
    portfolio: { ...canonicalPreset.spec.portfolio, rank: null },
    delisting: { assumed_return: 0 },
  },
  spec_hash: "f62a573942cd9cea91535597a86307047874cf788c5639040e2e5b9ed7298102",
  data_version: "20261111T030742Z",
  engine_version: "1.0.0",
  git_sha: "b6e4d794dfbdccf4d9cb47f1399fa75d58ea5e99",
  result: {
    metrics: {
      periods: 36,
      start: { session: "2020-01-02", price: "close" },
      end: { session: "2022-12-30", price: "close" },
      years: 2.99247091034,
      total_return: 0.607593345045,
      cagr: 0.171920938402,
      volatility: 0.233107664009,
      sharpe: 0.76931736638,
      max_drawdown: -0.219983829601,
      turnover: 0.619317672375,
      hit_rate: 0.638888888889,
      benchmark_total_return: 0.235506339085,
      benchmark_cagr: 0.0732280633733,
      excess_return: 0.0986928750289,
      beta: 0.925349193036,
      alpha: 0.0964331018474,
      mean_excess_return: 0.00747906115565,
      excess_t_stat: 1.49991803288,
    },
    periods: [
      {
        decision: "2020-06-01",
        decision_time: "2020-06-01T09:30:00-04:00",
        fill_time: "2020-06-01T16:00:00-04:00",
        fill: { session: "2020-06-01", price: "close" },
        end: { session: "2020-07-01", price: "close" },
        universe_size: 40,
        holdings: 10,
        trades: 11,
        turnover: 1.0,
        cost: 0.001,
        gross_return: 0.0412202997571,
        net_return: 0.0401790794573,
        benchmark_return: 0.0207644055197,
        risk_free_rate: 0.14,
        value: 1.03779739024,
      },
    ],
    equity_curve: [
      { at: { session: "2020-01-02", price: "close" }, value: 1.0, benchmark: 1.0 },
      {
        at: { session: "2020-02-03", price: "close" },
        value: 1.01781499491,
        benchmark: 0.997691384246,
      },
    ],
    warnings: [
      {
        kind: "missing_signal",
        decision: "2020-04-01",
        message:
          "KSS was left out at the 2020-04-01 decision, because rev_accel had no value. Revenue for the quarter a year before the one that ended on 2019-11-02 wasn't known.",
        ticker: "KSS",
        signal: "rev_accel",
      },
    ],
  },
} satisfies GetResponse<"/v1/backtests/{run_id}">;
