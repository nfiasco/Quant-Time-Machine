import { describe, expect, it } from "vitest";

import { fixedAssumptions, specAssumptions } from "@/features/backtests/assumptions";
import { succeededRun } from "@/features/backtests/fixtures/backtest-run";

const SPEC = succeededRun.spec;

describe("specAssumptions", () => {
  it("writes out the canonical spec's choices", () => {
    expect(specAssumptions(SPEC)).toEqual([
      {
        term: "Decisions",
        detail: "Monthly, on the first trading day at 09:30 ET, using only what was public by then",
      },
      {
        term: "Fills",
        detail:
          "At the decision day's close, 4:00 PM ET or 1:00 PM on an early-close day, so a decision never sees the bar it trades at",
      },
      { term: "Costs", detail: "10 bps of the value traded, on every trade" },
      { term: "Delistings", detail: "Valued at the last close, for a holding that stops trading" },
      { term: "Benchmark", detail: "SPY, its total return between the same prices" },
      { term: "Universe", detail: "Starter large caps, as its membership was at each decision" },
    ]);
  });

  it("follows the spec's fill rule and delisting return", () => {
    const found = specAssumptions({
      ...SPEC,
      schedule: { ...SPEC.schedule, fill: "next_day_open" },
      delisting: { assumed_return: -0.3 },
    });
    expect(found[1].detail).toBe("At the next session's open, the day after each decision");
    expect(found[3].detail).toBe(
      "Valued at the last close less 30%, for a holding that stops trading",
    );
  });
});

describe("fixedAssumptions", () => {
  it("lists what every run assumes", () => {
    expect(fixedAssumptions(SPEC)).toHaveLength(5);
    expect(fixedAssumptions(SPEC)[0]).toBe("Cash earns nothing.");
  });

  it("adds free shorting for a long-short spec", () => {
    const longShort = {
      ...SPEC,
      portfolio: {
        weighting: "equal" as const,
        long_only: false,
        rank: { signal: "mom_12_1", quantiles: 5, long: "top" as const },
      },
    };
    expect(fixedAssumptions(longShort).at(-1)).toBe(
      "Shorting is free and always possible: no borrow fee, margin, or recall.",
    );
  });
});
