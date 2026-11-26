import { describe, expect, it } from "vitest";

import { membersJune, holdingsJune } from "@/features/backtests/fixtures/backtest-results";
import { succeededRun } from "@/features/backtests/fixtures/backtest-run";
import {
  describeCounts,
  describeOutcome,
  heldCount,
  holdingRows,
  memberRows,
} from "@/features/backtests/members";
import type { BacktestMember } from "@/lib/api/types";

const SPEC = succeededRun.spec;
// The documented members, as their route's type: the literal's `{}` reasons widen otherwise.
const [ABBV, AAPL, KSS] = membersJune.members as BacktestMember[];
const PERIOD_END = { session: "2020-07-01", price: "close" } as const;

function member(changes: Partial<BacktestMember>): BacktestMember {
  return { ...ABBV, ...changes };
}

describe("describeOutcome", () => {
  it("says why Apple wasn't held on June 1, 2020 (eval task T5)", () => {
    expect(describeOutcome(AAPL, SPEC)).toEqual({
      status: "out",
      label: "Not held",
      detail: "Failed rev_accel > 0",
    });
  });

  it("marks a held member, whose weight says the rest", () => {
    expect(describeOutcome(ABBV, SPEC)).toEqual({ status: "held", label: "Held", detail: "" });
    expect(describeOutcome(member({ weight: -0.25 }), SPEC).label).toBe("Held short");
  });

  it("gives the reason a signal had no value", () => {
    expect(describeOutcome(KSS, SPEC)).toEqual({
      status: "out",
      label: "Left out",
      detail:
        "No rev_accel value: Revenue for the quarter a year before the one that ended on 2019-11-02 wasn't known.",
    });
  });

  it("lists every filter a member failed", () => {
    expect(describeOutcome(member({ outcome: "failed_filter", failed: [0, 1] }), SPEC).detail).toBe(
      "Failed rev_accel > 0 and mom_12_1 > 0",
    );
  });

  it("says where a member stood in a ranking", () => {
    const ranked = {
      ...SPEC,
      portfolio: {
        ...SPEC.portfolio,
        rank: { signal: "mom_12_1", quantiles: 5, long: "top" as const },
      },
    };
    expect(describeOutcome(member({ outcome: "outside_ranking", rank: 12 }), ranked).detail).toBe(
      "Passed every filter, but ranked 12th by mom_12_1, outside the end the portfolio holds",
    );
    expect(describeOutcome(member({ outcome: "outside_ranking", rank: 23 }), ranked).detail).toBe(
      "Passed every filter, but ranked 23rd by mom_12_1, outside the end the portfolio holds",
    );
  });

  it("tells a choice that wasn't traded from a holding", () => {
    expect(describeOutcome(member({ outcome: "no_fill_price" }), SPEC)).toMatchObject({
      status: "chosen",
      label: "Chosen, not bought",
    });
    expect(describeOutcome(member({ outcome: "wiped_out" }), SPEC)).toMatchObject({
      status: "chosen",
      detail: "The run ended at this decision, before its trades",
    });
    expect(describeOutcome(member({ outcome: "stopped_trading", weight: null }), SPEC).label).toBe(
      "Left out",
    );
  });
});

describe("memberRows", () => {
  it("lists the held first, then why the rest weren't, with each holding's return", () => {
    const rows = memberRows([KSS, AAPL, ABBV], holdingsJune.holdings, SPEC, PERIOD_END);

    expect(rows.map((row) => [row.ticker, row.label])).toEqual([
      ["ABBV", "Held"],
      ["AAPL", "Not held"],
      ["KSS", "Left out"],
    ]);
    expect(rows[0]).toMatchObject({ periodReturn: 0.0930540242558, valuedEarly: null });
    expect(rows[1]).toMatchObject({
      signals: { mom_12_1: 0.693680328621, rev_accel: -0.0839275653488 },
      periodReturn: null,
    });
    expect(heldCount(rows)).toEqual({ held: 1, total: 3 });
  });

  it("says when a holding was valued before its period's end", () => {
    const [abbv] = memberRows([ABBV], holdingsJune.holdings, SPEC, {
      session: "2020-08-03",
      price: "close",
    });
    expect(abbv.valuedEarly).toBe("Valued at its last close, on Jul 1, 2020");
  });
});

describe("holdingRows", () => {
  it("lists a run's holdings when it kept no members record", () => {
    expect(holdingRows(holdingsJune.holdings, PERIOD_END)).toEqual([
      {
        key: "ABBV",
        ticker: "ABBV",
        name: null,
        cik: null,
        outcome: "held",
        status: "held",
        label: "Held",
        detail: "",
        weight: 0.1,
        signals: { mom_12_1: 0.134527265701, rev_accel: 0.0530041743358 },
        periodReturn: 0.0930540242558,
        valuedEarly: null,
      },
    ]);
  });
});

describe("describeCounts", () => {
  it("sums up a rebalance's members by what became of them", () => {
    const rows = memberRows([KSS, AAPL, ABBV], holdingsJune.holdings, SPEC, PERIOD_END);
    expect(describeCounts(rows)).toBe(
      "3 members: 1 held, 1 failed a filter, and 1 left out for a missing signal.",
    );
    expect(describeCounts(rows.slice(0, 1))).toBe("1 member: 1 held.");
  });

  it("says when there were none", () => {
    expect(describeCounts([])).toBe("The universe had no members at this decision.");
  });
});
