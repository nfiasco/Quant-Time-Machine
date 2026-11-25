import { describe, expect, it } from "vitest";

import {
  chooseDecision,
  decisionDays,
  decisionHref,
  formatDay,
} from "@/features/backtests/decisions";
import { succeededRun } from "@/features/backtests/fixtures/backtest-run";
import type { BacktestPeriod, BacktestWarning } from "@/lib/api/types";

const [JUNE] = succeededRun.result.periods;

function period(decision: string): BacktestPeriod {
  return { ...JUNE, decision };
}

function warning(kind: BacktestWarning["kind"], decision: string): BacktestWarning {
  return { kind, decision, message: "", ticker: null, signal: null };
}

const DAYS = ["2020-04-01", "2020-05-01", "2020-06-01", "2020-07-01"];

describe("decisionDays", () => {
  it("lists each decision that traded, in order", () => {
    // api-v1.md's run: its one documented period, and a warning from an earlier decision
    // that traded too.
    expect(decisionDays(succeededRun.result)).toEqual(["2020-06-01"]);
    expect(
      decisionDays({ periods: [period("2020-07-01"), period("2020-06-01")], warnings: [] }),
    ).toEqual(["2020-06-01", "2020-07-01"]);
  });

  it("adds a decision the run ended on, which has no period", () => {
    const result = {
      periods: [period("2020-06-01")],
      warnings: [warning("wiped_out", "2020-06-01"), warning("stopped_trading", "2020-07-01")],
    };
    expect(decisionDays(result)).toEqual(["2020-06-01", "2020-07-01"]);
  });

  it("leaves out a skipped decision", () => {
    const result = {
      periods: [period("2020-06-01")],
      warnings: [warning("fill_after_end", "2020-07-01")],
    };
    expect(decisionDays(result)).toEqual(["2020-06-01"]);
  });
});

describe("chooseDecision", () => {
  it("shows the last decision when the address names none", () => {
    expect(chooseDecision(DAYS, undefined)).toEqual({
      day: "2020-07-01",
      previous: "2020-06-01",
      next: null,
      notice: null,
    });
  });

  it("shows the decision the address names, with its neighbors", () => {
    expect(chooseDecision(DAYS, "2020-06-01")).toEqual({
      day: "2020-06-01",
      previous: "2020-05-01",
      next: "2020-07-01",
      notice: null,
    });
    expect(chooseDecision(DAYS, ["2020-04-01", "2020-05-01"])?.day).toBe("2020-04-01");
  });

  it("shows the decision before a day without one, and says so", () => {
    expect(chooseDecision(DAYS, "2020-06-05")).toMatchObject({
      day: "2020-06-01",
      notice:
        "The run made no decision on June 5, 2020, so this shows the one before it, on June 1, 2020.",
    });
  });

  it("shows the first decision for a day before it", () => {
    expect(chooseDecision(DAYS, "2019-12-31")).toMatchObject({
      day: "2020-04-01",
      previous: null,
      notice:
        "The run's first decision was on April 1, 2020, after December 31, 2019, so this shows that one.",
    });
  });

  it("shows the last decision for something that isn't a date", () => {
    expect(chooseDecision(DAYS, "June")).toMatchObject({
      day: "2020-07-01",
      notice: "“June” isn't a date such as 2020-06-01, so this shows the last decision.",
    });
  });

  it("has nothing to show for a run without decisions", () => {
    expect(chooseDecision([], "2020-06-01")).toBeNull();
  });
});

describe("decisionHref", () => {
  it("links to the run's page at a decision", () => {
    expect(decisionHref("abc", "2020-06-01")).toBe("/backtests/abc?decision=2020-06-01");
    expect(decisionHref("abc", "2020-06-01", { anchor: true })).toBe(
      "/backtests/abc?decision=2020-06-01#rebalance",
    );
  });
});

describe("formatDay", () => {
  it("writes a decision's day as people do", () => {
    expect(formatDay("2020-06-01")).toBe("June 1, 2020");
  });
});
