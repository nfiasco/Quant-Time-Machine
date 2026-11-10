import { describe, expect, it } from "vitest";

import { formatMacroValue, formatNumber, formatUsd, formatUsdMillions } from "@/lib/format";

describe("formatUsd", () => {
  it("prints a price with cents", () => {
    expect(formatUsd(322.32)).toBe("$322.32");
    expect(formatUsd(1234.5)).toBe("$1,234.50");
  });
});

describe("formatUsdMillions", () => {
  it("prints revenue in millions, as filings report it", () => {
    expect(formatUsdMillions(58_313_000_000)).toBe("$58,313 million");
    expect(formatUsdMillions(5_985_000_000)).toBe("$5,985 million");
  });

  it("writes out amounts under a million", () => {
    expect(formatUsdMillions(950_000)).toBe("$950,000");
  });

  it("keeps a minus sign", () => {
    expect(formatUsdMillions(-2_000_000)).toBe("−$2 million");
  });
});

describe("formatNumber", () => {
  it("groups thousands and keeps up to three decimals", () => {
    expect(formatNumber(133326)).toBe("133,326");
    expect(formatNumber(19477.4441)).toBe("19,477.444");
  });
});

describe("formatMacroValue", () => {
  it("adds a percent sign for series in percent", () => {
    expect(formatMacroValue(13.3, "Percent")).toBe("13.3%");
    expect(formatMacroValue(0.05, "Percent")).toBe("0.05%");
  });

  it("prints other units as the number alone", () => {
    expect(formatMacroValue(256.389, "Index 1982-1984=100")).toBe("256.389");
    expect(formatMacroValue(151000, "Thousands of Persons")).toBe("151,000");
  });

  it("says when a value was published as missing", () => {
    expect(formatMacroValue(null, "Percent")).toBe("no value");
  });
});
