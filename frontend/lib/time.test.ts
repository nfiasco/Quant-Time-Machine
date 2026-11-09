import { describe, expect, it } from "vitest";

import {
  etDateTimeOf,
  formatEtDateTime,
  formatPeriod,
  instantOf,
  parseAsOf,
  parseIsoDate,
  toAsOfParam,
} from "@/lib/time";

describe("parseAsOf", () => {
  it("reads a bare date as 09:30 ET (roadmap §2.2)", () => {
    expect(parseAsOf("2020-06-05")).toEqual({ year: 2020, month: 6, day: 5, hour: 9, minute: 30 });
  });

  it("reads a New York time and drops seconds", () => {
    expect(parseAsOf("2020-06-05T08:30:59")).toEqual({
      year: 2020,
      month: 6,
      day: 5,
      hour: 8,
      minute: 30,
    });
  });

  it("rejects offsets and dates that don't exist", () => {
    expect(parseAsOf("2020-06-05T13:30Z")).toBeNull();
    expect(parseAsOf("2020-02-30")).toBeNull();
    expect(parseAsOf("banana")).toBeNull();
  });

  it("round-trips through toAsOfParam", () => {
    expect(toAsOfParam(parseAsOf("2020-06-05")!)).toBe("2020-06-05T09:30");
  });
});

describe("etDateTimeOf", () => {
  it("reads the ET wall-clock time of an API timestamp", () => {
    expect(etDateTimeOf("2020-06-05T08:30:00-04:00")).toEqual({
      year: 2020,
      month: 6,
      day: 5,
      hour: 8,
      minute: 30,
    });
    expect(formatEtDateTime(etDateTimeOf("2020-04-30T18:03:10-04:00")!)).toBe(
      "April 30, 2020, 6:03 PM ET",
    );
  });

  it("handles fractions of a second", () => {
    expect(etDateTimeOf("2001-03-30T23:59:59.999999-05:00")).toMatchObject({
      hour: 23,
      minute: 59,
    });
  });
});

describe("instantOf", () => {
  it("is the absolute instant", () => {
    expect(instantOf("2020-06-05T09:30:00-04:00")).toBe(Date.UTC(2020, 5, 5, 13, 30));
  });

  it("orders times across the end of daylight saving time", () => {
    // 1:30 AM EDT happens before 1:15 AM EST on November 1, 2020.
    expect(instantOf("2020-11-01T01:30:00-04:00")).toBeLessThan(
      instantOf("2020-11-01T01:15:00-05:00"),
    );
  });

  it("keeps microseconds, so an assumed end of day stays before the next day", () => {
    const endOfDay = instantOf("2001-03-30T23:59:59.999999-05:00");
    expect(endOfDay).toBeGreaterThan(instantOf("2001-03-30T23:59:59.999-05:00"));
    expect(endOfDay).toBeLessThan(instantOf("2001-03-31T00:00:00-05:00"));
  });

  it("is NaN for a malformed value", () => {
    expect(instantOf("not a time")).toBeNaN();
  });
});

describe("parseIsoDate", () => {
  it("reads a calendar date and rejects anything else", () => {
    expect(parseIsoDate("2020-06-04")).toEqual({ year: 2020, month: 6, day: 4 });
    expect(parseIsoDate("2020-06-04T16:00")).toBeNull();
    expect(parseIsoDate("2021-02-29")).toBeNull();
  });
});

describe("formatPeriod", () => {
  it("names a period the way people say it", () => {
    expect(formatPeriod("2020-05-01", "Monthly")).toBe("May 2020");
    expect(formatPeriod("2020-04-01", "Quarterly")).toBe("Q2 2020");
    expect(formatPeriod("2020-01-01", "Annual")).toBe("2020");
    expect(formatPeriod("2020-06-04", "Daily")).toBe("Jun 4, 2020");
  });

  it("returns a malformed period unchanged", () => {
    expect(formatPeriod("2020-05", "Monthly")).toBe("2020-05");
  });
});
