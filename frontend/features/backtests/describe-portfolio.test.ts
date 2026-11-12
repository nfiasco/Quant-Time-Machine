import { describe, expect, it } from "vitest";

import { describePortfolio } from "@/features/backtests/describe-portfolio";

describe("describePortfolio", () => {
  it("describes a portfolio of everything that passes the filters", () => {
    expect(describePortfolio({ weighting: "equal", long_only: true })).toBe(
      "Equal weight, long only",
    );
    expect(describePortfolio({ weighting: "value", long_only: true })).toBe(
      "Value weight, long only",
    );
  });

  it("treats a ranking that is null like one that is left out", () => {
    // A spec the engine saved states that it had no ranking.
    expect(describePortfolio({ weighting: "equal", long_only: true, rank: null })).toBe(
      "Equal weight, long only",
    );
  });

  it("names the end of the ranking a long-only portfolio holds", () => {
    expect(
      describePortfolio({
        weighting: "equal",
        long_only: true,
        rank: { signal: "mom_12_1", quantiles: 5, long: "top" },
      }),
    ).toBe("Top quintile by mom_12_1, equal weight, long only");
    expect(
      describePortfolio({
        weighting: "equal",
        long_only: true,
        rank: { signal: "rev_growth", quantiles: 10, long: "bottom" },
      }),
    ).toBe("Bottom decile by rev_growth, equal weight, long only");
  });

  it("says which end a long-short portfolio is long, and which short", () => {
    expect(
      describePortfolio({
        weighting: "equal",
        long_only: false,
        rank: { signal: "mom_12_1", quantiles: 5, long: "top" },
      }),
    ).toBe("Long the top quintile by mom_12_1 and short the bottom, equal weight");
    expect(
      describePortfolio({
        weighting: "equal",
        long_only: false,
        rank: { signal: "mom_12_1", quantiles: 3, long: "bottom" },
      }),
    ).toBe("Long the bottom third by mom_12_1 and short the top, equal weight");
  });

  it("names halves, thirds, quartiles, quintiles, and deciles, and counts the rest", () => {
    const describeTop = (quantiles: number) =>
      describePortfolio({
        weighting: "equal",
        long_only: true,
        rank: { signal: "mom", quantiles, long: "top" },
      });

    expect([2, 3, 4, 5, 10].map(describeTop)).toEqual([
      "Top half by mom, equal weight, long only",
      "Top third by mom, equal weight, long only",
      "Top quartile by mom, equal weight, long only",
      "Top quintile by mom, equal weight, long only",
      "Top decile by mom, equal weight, long only",
    ]);
    expect(describeTop(7)).toBe("Top of 7 quantiles by mom, equal weight, long only");
  });
});
