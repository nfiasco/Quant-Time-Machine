import { describe, expect, it } from "vitest";

import { succeededRun } from "@/features/backtests/fixtures/backtest-run";
import { metricGroups } from "@/features/backtests/metric-rows";
import type { BacktestMetrics } from "@/lib/api/types";

const METRICS = succeededRun.result.metrics;

function rows(metrics: BacktestMetrics, benchmarkMaxDrawdown: number | null = -0.2) {
  return Object.fromEntries(
    metricGroups(metrics, { benchmarkMaxDrawdown })
      .flatMap((group) => group.rows)
      .map((row) => [row.label, row]),
  );
}

describe("metricGroups", () => {
  it("groups every metric, after costs", () => {
    expect(
      metricGroups(METRICS, { benchmarkMaxDrawdown: null }).map((group) => [
        group.title,
        group.rows.map((row) => row.label),
      ]),
    ).toEqual([
      ["Growth", ["Total return", "Growth of $1", "Annual return (CAGR)"]],
      ["Risk", ["Volatility", "Sharpe ratio", "Max drawdown"]],
      [
        "Against the benchmark",
        ["Excess return", "Hit rate", "Beta", "Alpha", "Mean monthly excess return", "t-statistic"],
      ],
      ["Trading", ["Turnover", "Periods"]],
    ]);
  });

  it("puts the run beside its benchmark, with signed returns", () => {
    // api-v1.md's run: the canonical spec from 2020 to 2022.
    const found = rows(METRICS);
    expect(found["Annual return (CAGR)"].strategy).toEqual({ text: "+17.2%", tone: "positive" });
    expect(found["Annual return (CAGR)"].benchmark).toEqual({ text: "+7.3%", tone: "positive" });
    expect(found["Total return"].strategy.text).toBe("+60.8%");
    expect(found["Growth of $1"].strategy.text).toBe("$1.61");
    expect(found["Growth of $1"].benchmark?.text).toBe("$1.24");
    expect(found["Sharpe ratio"].strategy.text).toBe("0.77");
    expect(found["Max drawdown"].strategy.text).toBe("−22.0%");
    expect(found["Excess return"].strategy).toEqual({ text: "+9.9%", tone: "positive" });
    expect(found["Hit rate"].strategy).toEqual({
      text: "63.9%",
      tone: null,
      detail: "23 of 36 months",
    });
    expect(found["Mean monthly excess return"].strategy.text).toBe("+0.75%");
    expect(found["t-statistic"].strategy.text).toBe("1.50");
    expect(found.Turnover.strategy.text).toBe("61.9%");
    expect(found.Periods.strategy).toEqual({ text: "36", tone: null, detail: "over 2.99 years" });
  });

  it("says where a benchmark value the engine doesn't give comes from", () => {
    const found = rows(METRICS, -0.237);
    expect(found["Max drawdown"].benchmark?.text).toBe("−23.7%");
    expect(found["Max drawdown"].benchmarkNote).toBe("curve");
    expect(found.Volatility.benchmark?.text).toBe("—");
    expect(found.Volatility.benchmarkNote).toBe("not-computed");
    // A row about the benchmark has no benchmark column.
    expect(found.Beta.benchmark).toBeNull();
  });

  it("shows a dash for what a run can't give", () => {
    const found = rows(
      {
        ...METRICS,
        cagr: null,
        sharpe: null,
        hit_rate: null,
        benchmark_total_return: null,
        benchmark_cagr: null,
      },
      null,
    );
    expect(found["Annual return (CAGR)"].strategy).toEqual({ text: "—", tone: null });
    expect(found["Sharpe ratio"].strategy.text).toBe("—");
    expect(found["Hit rate"].strategy.text).toBe("—");
    expect(found["Growth of $1"].benchmark?.text).toBe("—");
    expect(found["Max drawdown"].benchmark?.text).toBe("—");
  });
});
