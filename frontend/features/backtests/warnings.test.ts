import { describe, expect, it } from "vitest";

import { canonicalCoverage } from "@/features/backtests/fixtures/backtest-results";
import { succeededRun } from "@/features/backtests/fixtures/backtest-run";
import {
  WARNING_LABELS,
  describeCoverage,
  groupWarnings,
  warningsAt,
  worstCoverageRows,
} from "@/features/backtests/warnings";
import type { BacktestWarning, CoverageReport } from "@/lib/api/types";

const [KSS] = succeededRun.result.warnings;

function warning(kind: BacktestWarning["kind"], decision: string): BacktestWarning {
  return { kind, decision, message: `${kind} on ${decision}`, ticker: null, signal: null };
}

const REPORT: CoverageReport = canonicalCoverage.coverage;

describe("WARNING_LABELS", () => {
  it("names every kind of warning the API documents", () => {
    expect(Object.keys(WARNING_LABELS).toSorted()).toEqual([
      "delisted_exit",
      "empty_portfolio",
      "fill_after_end",
      "missing_benchmark",
      "missing_price",
      "missing_risk_free",
      "missing_signal",
      "no_fill_price",
      "stopped_trading",
      "thin_ranking",
      "wiped_out",
    ]);
  });
});

describe("groupWarnings", () => {
  it("groups warnings by kind, what changes the result first", () => {
    const groups = groupWarnings([
      KSS,
      warning("delisted_exit", "2019-11-01"),
      warning("missing_signal", "2020-05-01"),
    ]);
    expect(groups.map((g) => [g.kind, g.warnings.length])).toEqual([
      ["delisted_exit", 1],
      ["missing_signal", 2],
    ]);
    expect(groups[1].title).toBe("Members left out for a missing signal");
  });

  it("has nothing for a run without warnings", () => {
    expect(groupWarnings([])).toEqual([]);
  });
});

describe("warningsAt", () => {
  it("keeps one decision's warnings", () => {
    const warnings = [
      KSS,
      warning("delisted_exit", "2020-04-01"),
      warning("wiped_out", "2020-05-01"),
    ];
    expect(warningsAt(warnings, "2020-04-01").map((w) => w.kind)).toEqual([
      "delisted_exit",
      "missing_signal",
    ]);
  });
});

describe("describeCoverage", () => {
  it("says how many member-decisions lacked data, and which", () => {
    // api-v1.md's coverage example: the canonical run from 2010 to 2025.
    expect(describeCoverage(REPORT)).toBe(
      "326 of 7,529 member-decisions (4.3%) over 192 decisions were left out for lack of data: 312 without fundamentals and 25 without prices. " +
        "3 holdings were valued at their last close before their periods ended.",
    );
  });

  it("says when nothing was left out", () => {
    const totals = {
      ...REPORT.totals,
      left_out: 0,
      exits: 0,
      missing: { fundamentals: 0, prices: 0 },
    };
    expect(describeCoverage({ ...REPORT, totals })).toBe(
      "None of 7,529 member-decisions over 192 decisions was left out for lack of data.",
    );
  });
});

describe("worstCoverageRows", () => {
  it("lists the security-years with the most left out", () => {
    const rows = worstCoverageRows(REPORT);
    expect(rows.map((row) => [row.ticker, row.year, row.left_out])).toEqual([["XOM", 2010, 12]]);
  });
});
