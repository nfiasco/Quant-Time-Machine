import { describe, expect, it } from "vitest";

import { describeDelisting } from "@/features/backtests/describe-delisting";

describe("describeDelisting", () => {
  it("keeps the last close without an assumption", () => {
    expect(describeDelisting(undefined)).toBe("Valued at the last close");
    // A spec the engine saved writes the default out.
    expect(describeDelisting({ assumed_return: 0 })).toBe("Valued at the last close");
  });

  it("names the loss assumed after the last close", () => {
    expect(describeDelisting({ assumed_return: -0.3 })).toBe("Valued at the last close less 30%");
    // -0.07 * 100 is 7.000000000000001 in floating point.
    expect(describeDelisting({ assumed_return: -0.07 })).toBe("Valued at the last close less 7%");
    expect(describeDelisting({ assumed_return: -0.125 })).toBe(
      "Valued at the last close less 12.5%",
    );
  });

  it("says a holding was written off at -100%", () => {
    expect(describeDelisting({ assumed_return: -1 })).toBe("Written off");
  });

  it("shows a dash for a field that isn't a number yet", () => {
    expect(describeDelisting({ assumed_return: Number.NaN })).toBe("—");
  });
});
