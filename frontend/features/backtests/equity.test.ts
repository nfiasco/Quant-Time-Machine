import { describe, expect, it } from "vitest";

import {
  chartPoints,
  curveSummary,
  deepest,
  drawdownScale,
  ticksAreYears,
  timeTicks,
} from "@/features/backtests/equity";
import { workedCurve, workedMaxDrawdown } from "@/features/backtests/fixtures/equity-curve";
import type { EquityPoint } from "@/lib/api/types";

describe("chartPoints", () => {
  it("draws both drawdowns from the curve, from a first peak of 1", () => {
    const points = chartPoints(workedCurve);

    expect(points.map((p) => p.session)).toEqual([
      "2021-01-04",
      "2021-02-01",
      "2021-03-01",
      "2021-04-01",
      "2021-04-30",
    ]);
    expect(points.map((p) => p.drawdown)).toEqual([
      0,
      expect.closeTo(-0.001, 12),
      expect.closeTo(-0.001999, 12),
      0,
      0,
    ]);
    // SPY peaked in February, at 1.02, and fell 1% by March.
    expect(points.map((p) => p.benchmarkDrawdown)).toEqual([0, 0, expect.closeTo(-0.01, 12), 0, 0]);
  });

  it("finds the drawdown metrics.md works by hand", () => {
    const trough = deepest(chartPoints(workedCurve), "drawdown");
    expect(trough?.session).toBe("2021-03-01");
    expect(trough?.depth).toBeCloseTo(workedMaxDrawdown, 12);
  });

  it("leaves the benchmark out from its first gap on", () => {
    const curve: EquityPoint[] = [
      ...workedCurve.slice(0, 2),
      { at: { session: "2021-03-01", price: "close" }, value: 0.9, benchmark: null },
      { at: { session: "2021-04-01", price: "close" }, value: 1.1, benchmark: 1.2 },
    ];
    const points = chartPoints(curve);
    expect(points.map((p) => p.benchmark)).toEqual([1, 1.02, null, null]);
    expect(points.map((p) => p.benchmarkDrawdown)).toEqual([0, 0, null, null]);
  });

  it("reaches −100% for a portfolio with nothing left", () => {
    const curve: EquityPoint[] = [
      workedCurve[0],
      { at: { session: "2021-02-01", price: "close" }, value: 0, benchmark: 1.01 },
    ];
    expect(chartPoints(curve)[1].drawdown).toBe(-1);
  });
});

describe("timeTicks", () => {
  it("labels months for a short run", () => {
    const ticks = timeTicks(chartPoints(workedCurve));
    expect(ticks).toEqual(["2021-01-04", "2021-02-01", "2021-03-01", "2021-04-01"]);
    expect(ticksAreYears(ticks)).toBe(false);
  });

  it("labels years for a long run, at most eight", () => {
    const curve: EquityPoint[] = [];
    for (let year = 2010; year <= 2025; year++) {
      for (const month of ["01", "07"]) {
        curve.push({
          at: { session: `${year}-${month}-01`, price: "close" },
          value: 1,
          benchmark: 1,
        });
      }
    }
    const ticks = timeTicks(chartPoints(curve));
    expect(ticks).toEqual([
      "2010-01-01",
      "2012-01-01",
      "2014-01-01",
      "2016-01-01",
      "2018-01-01",
      "2020-01-01",
      "2022-01-01",
      "2024-01-01",
    ]);
    expect(ticksAreYears(ticks)).toBe(true);
  });
});

describe("curveSummary", () => {
  it("says where $1 ended and how far each fell", () => {
    expect(curveSummary(chartPoints(workedCurve), "SPY")).toBe(
      "After costs, $1 in the portfolio at the close on Jan 4, 2021 was worth $1.13 at the close on Apr 30, 2021, and $1 in SPY was worth $1.05. " +
        "The portfolio's deepest fall from a peak was −0.2%, at the close on Mar 1, 2021; SPY's was −1.0%, on Mar 1, 2021.",
    );
  });

  it("says when there's nothing to chart", () => {
    expect(curveSummary([], "SPY")).toBe("The run has no equity curve.");
  });
});

describe("drawdownScale", () => {
  function fallingTo(depth: number, benchmark = 0) {
    return chartPoints([
      { at: { session: "2020-01-02", price: "close" }, value: 1, benchmark: 1 },
      { at: { session: "2020-02-03", price: "close" }, value: 1 + depth, benchmark: 1 + benchmark },
    ]);
  }

  it("steps evenly from a round floor below the deepest fall to 0", () => {
    // The canonical run: −22.0%, and SPY's −23.8%.
    expect(drawdownScale(fallingTo(-0.22, -0.2377))).toEqual({
      floor: -0.25,
      ticks: [-0.25, -0.2, -0.15, -0.1, -0.05, 0],
    });
  });

  it("uses finer steps for a shallow fall, and coarser for a deep one", () => {
    expect(drawdownScale(fallingTo(-0.001999)).ticks).toEqual([-0.01, 0]);
    expect(drawdownScale(fallingTo(-1)).ticks).toEqual([-1, -0.8, -0.6, -0.4, -0.2, 0]);
  });

  it("keeps a floor for a run that never fell", () => {
    expect(drawdownScale(fallingTo(0.1, 0.1))).toEqual({ floor: -0.01, ticks: [-0.01, 0] });
  });
});
