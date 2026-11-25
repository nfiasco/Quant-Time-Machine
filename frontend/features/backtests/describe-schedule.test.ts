import { describe, expect, it } from "vitest";

import {
  FILL_LABELS,
  describeDecision,
  describeFilter,
} from "@/features/backtests/describe-schedule";

describe("describeDecision", () => {
  it("reads the spec's decision time as people say it", () => {
    expect(describeDecision("first_trading_day 09:30 America/New_York")).toBe(
      "first trading day at 09:30 ET",
    );
  });

  it("leaves a form it doesn't know as it is", () => {
    expect(describeDecision("last_trading_day 15:00 America/New_York")).toBe(
      "last_trading_day 15:00 America/New_York",
    );
  });
});

describe("FILL_LABELS", () => {
  it("names both fill rules", () => {
    expect(FILL_LABELS).toEqual({
      same_day_close: "Same-day close",
      next_day_open: "Next-day open",
    });
  });
});

describe("describeFilter", () => {
  it("writes a filter as the spec reads", () => {
    expect(describeFilter({ signal: "rev_accel", op: ">", value: 0 })).toBe("rev_accel > 0");
    expect(describeFilter({ signal: "mom_12_1", op: "<=", value: -0.05 })).toBe(
      "mom_12_1 <= -0.05",
    );
  });

  it("marks what a form can't read yet", () => {
    expect(describeFilter({ signal: "", op: ">", value: Number.NaN })).toBe("? > ?");
  });
});
