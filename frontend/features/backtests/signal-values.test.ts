import { describe, expect, it } from "vitest";

import { formatSignalValue, signalUnit } from "@/features/backtests/signal-values";
import type { SignalSpec } from "@/features/backtests/types";

const MOMENTUM: SignalSpec = { type: "momentum", lookback_months: 12, skip_months: 1 };
const ACCELERATION: SignalSpec = { type: "revenue_growth_acceleration", basis: "yoy_quarterly" };
const UNRATE: SignalSpec = {
  type: "macro_change",
  series: "UNRATE",
  releases: 3,
  change: "absolute",
};

describe("formatSignalValue", () => {
  it("reads momentum and revenue growth as signed percentages", () => {
    // ABBV's momentum at the June 1, 2020 decision (api-v1.md's holdings example).
    expect(formatSignalValue(0.134527265701, MOMENTUM)).toBe("+13.5%");
    expect(formatSignalValue(-0.2, { type: "revenue_growth", basis: "yoy_quarterly" })).toBe(
      "−20.0%",
    );
  });

  it("reads an acceleration in percentage points", () => {
    // Apple's at the same decision: growth slowed by 8.39 points (signals.md).
    expect(formatSignalValue(-0.0839, ACCELERATION)).toBe("−8.39 pts");
  });

  it("reads a macro change in its series' units, or as a percentage", () => {
    expect(formatSignalValue(0.3, UNRATE)).toBe("+0.3");
    expect(formatSignalValue(-0.25, { ...UNRATE, change: "relative" })).toBe("−25.0%");
  });

  it("shows a number for a kind it doesn't know, and a dash for no value", () => {
    expect(formatSignalValue(1.5, undefined)).toBe("+1.5");
    expect(formatSignalValue(null, MOMENTUM)).toBe("—");
    expect(formatSignalValue(undefined, MOMENTUM)).toBe("—");
  });
});

describe("signalUnit", () => {
  it("names the unit for a column's header", () => {
    expect(signalUnit(MOMENTUM)).toBe("%");
    expect(signalUnit(ACCELERATION)).toBe("pts");
    expect(signalUnit(UNRATE)).toBe("UNRATE units");
    expect(signalUnit(undefined)).toBeNull();
  });
});
