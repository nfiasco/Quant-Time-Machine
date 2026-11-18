import { describe, expect, it } from "vitest";

import { canonicalPreset } from "@/features/backtests/presets";
import type { ExperimentSpec } from "@/features/backtests/types";
import { delistingFromLoss, delistingLoss, validateSpec } from "@/features/backtests/validation";

function withDelisting(assumed_return: number): ExperimentSpec {
  return { ...canonicalPreset.spec, delisting: { assumed_return } };
}

describe("validateSpec", () => {
  it("accepts the canonical example, which leaves the delisting rule out", () => {
    expect(validateSpec(canonicalPreset.spec)).toEqual({});
  });

  it("accepts a delisting loss from 0 to 100%", () => {
    for (const assumed of [0, -0.3, -1]) {
      expect(validateSpec(withDelisting(assumed))).toEqual({});
    }
  });

  it("rejects a delisting loss outside 0 to 100%, under the API's field path", () => {
    expect(validateSpec(withDelisting(-1.5))).toEqual({
      "delisting.assumed_return": "The loss must be from 0 to 100%.",
    });
    expect(validateSpec(withDelisting(0.1))).toEqual({
      "delisting.assumed_return": "The loss must be from 0 to 100%.",
    });
    expect(validateSpec(withDelisting(Number.NaN))).toEqual({
      "delisting.assumed_return": "Enter a loss from 0 to 100%.",
    });
  });
});

describe("the delisting loss field", () => {
  it("shows the assumed return as a loss in percent", () => {
    expect(delistingLoss(undefined)).toBe("0");
    expect(delistingLoss({ assumed_return: -0.3 })).toBe("30");
    expect(delistingLoss({ assumed_return: -0.07 })).toBe("7");
    expect(delistingLoss({ assumed_return: -1 })).toBe("100");
  });

  it("turns the loss back into the assumed return", () => {
    expect(delistingFromLoss("30")).toEqual({ assumed_return: -0.3 });
    expect(delistingFromLoss("100")).toEqual({ assumed_return: -1 });
    expect(delistingFromLoss(" ").assumed_return).toBeNaN();
  });
});
