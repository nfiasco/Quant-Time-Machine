import { describe, expect, it } from "vitest";

import { describeSignal } from "@/features/backtests/describe-signal";

describe("describeSignal", () => {
  it("describes momentum, 12-1 when the spec leaves out its parameters", () => {
    expect(describeSignal({ type: "momentum" })).toBe(
      "Momentum, 12-month lookback, skipping the last 1",
    );
    expect(describeSignal({ type: "momentum", lookback_months: 6, skip_months: 0 })).toBe(
      "Momentum, 6-month lookback, skipping the last 0",
    );
  });

  it("describes revenue growth and its acceleration", () => {
    expect(describeSignal({ type: "revenue_growth", basis: "yoy_quarterly" })).toBe(
      "Revenue growth (year over year, quarterly)",
    );
    expect(
      describeSignal({ type: "revenue_growth_acceleration", basis: "yoy_quarterly" }),
    ).toBe("Revenue growth acceleration (year over year, quarterly)");
  });

  it("describes a macro change, with one release or several", () => {
    expect(
      describeSignal({ type: "macro_change", series: "UNRATE", releases: 1, change: "absolute" }),
    ).toBe("UNRATE's absolute change over its last 1 release");
    expect(
      describeSignal({
        type: "macro_change",
        series: "CPIAUCSL",
        releases: 12,
        change: "relative",
      }),
    ).toBe("CPIAUCSL's relative change over its last 12 releases");
  });
});
