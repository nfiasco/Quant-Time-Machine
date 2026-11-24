import { describe, expect, it } from "vitest";

import { succeededRun } from "@/features/backtests/fixtures/backtest-run";
import { describeProgress, describeRun, headlineMetrics } from "@/features/backtests/run-status";

// Statuses, progress, and errors as api-v1.md documents them (GET /v1/backtests/{run_id}).
describe("describeRun", () => {
  it("keeps refreshing a queued run", () => {
    expect(describeRun({ status: "queued", progress: null, error: null })).toMatchObject({
      label: "Queued",
      pending: true,
      progress: null,
    });
  });

  it("reports a running run's decisions done out of its total", () => {
    const state = describeRun({
      status: "running",
      progress: { decisions_done: 13, decisions_total: 36 },
      error: null,
    });
    expect(state).toMatchObject({
      label: "Running",
      pending: true,
      progress: { done: 13, total: 36, percent: 36 },
    });
    expect(describeProgress(state.progress!)).toBe("13 of 36 decisions");
  });

  it("has no progress for a moment after a run starts", () => {
    expect(describeRun({ status: "running", progress: null, error: null }).progress).toBeNull();
  });

  it("keeps the live sentence the same while the count moves", () => {
    const early = describeRun({
      status: "running",
      progress: { decisions_done: 6, decisions_total: 36 },
      error: null,
    });
    const late = describeRun({
      status: "running",
      progress: { decisions_done: 34, decisions_total: 36 },
      error: null,
    });
    expect(early.sentence).toBe(late.sentence);
  });

  it("stops refreshing a finished run, failed or not", () => {
    expect(describeRun(succeededRun)).toMatchObject({ label: "Succeeded", pending: false });
    const restarted = "The server restarted before this run finished. Submit it again.";
    expect(describeRun({ status: "failed", progress: null, error: restarted })).toMatchObject({
      label: "Failed",
      pending: false,
      sentence: "The run failed, so it has no result.",
    });
  });
});

describe("headlineMetrics", () => {
  it("shows the run's returns beside its benchmark's, with their signs", () => {
    expect(headlineMetrics(succeededRun.result.metrics, "SPY")).toEqual([
      {
        label: "Annual return (CAGR)",
        value: "+17.2%",
        detail: "SPY: +7.3%",
        tone: "positive",
      },
      { label: "Total return", value: "+60.8%", detail: "SPY: +23.6%", tone: "positive" },
      {
        label: "Sharpe ratio",
        value: "0.77",
        detail: "Volatility 23.3% a year",
        tone: null,
      },
      {
        label: "Max drawdown",
        value: "−22.0%",
        detail: "The deepest fall from an earlier peak",
        tone: null,
      },
    ]);
  });

  it("says when the run can't give a metric", () => {
    const metrics = {
      ...succeededRun.result.metrics,
      cagr: null,
      sharpe: null,
      volatility: null,
      benchmark_cagr: null,
    };
    const [cagr, , sharpe] = headlineMetrics(metrics, "SPY");
    expect(cagr).toMatchObject({ value: "—", detail: "SPY: not available", tone: null });
    expect(sharpe).toMatchObject({ value: "—", detail: "Volatility not available" });
  });
});
