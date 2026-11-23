import { describe, expect, it } from "vitest";

import {
  formatMacroValue,
  formatNumber,
  formatPercent,
  formatRatio,
  formatUsd,
  formatUsdMillions,
} from "@/lib/format";

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

// Values from the API's documented run (api-v1.md, GET /v1/backtests/{run_id}).
describe("formatPercent", () => {
  it("prints a fraction as a percentage with one decimal", () => {
    expect(formatPercent(0.171920938402)).toBe("17.2%");
    expect(formatPercent(0.0732280633733)).toBe("7.3%");
    expect(formatPercent(12.345)).toBe("1,234.5%");
  });

  it("keeps a loss's minus sign, and adds a plus to a gain when asked", () => {
    expect(formatPercent(-0.219983829601)).toBe("−22.0%");
    expect(formatPercent(0.607593345045, { signed: true })).toBe("+60.8%");
    expect(formatPercent(-0.219983829601, { signed: true })).toBe("−22.0%");
  });

  it("gives no sign to a value that rounds to zero", () => {
    expect(formatPercent(-0.0004, { signed: true })).toBe("0.0%");
    expect(formatPercent(0, { signed: true })).toBe("0.0%");
  });
});

describe("formatRatio", () => {
  it("prints two decimals with a minus sign for a negative", () => {
    expect(formatRatio(0.76931736638)).toBe("0.77");
    expect(formatRatio(-0.25)).toBe("−0.25");
    expect(formatRatio(-0.001)).toBe("0.00");
  });
});
