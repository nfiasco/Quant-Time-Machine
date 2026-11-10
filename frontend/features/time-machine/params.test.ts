import { describe, expect, it } from "vitest";

import {
  MAX_ENTRIES,
  catalogAsOf,
  demoQuery,
  explorerHref,
  fieldErrorsFromFailure,
  parseEntries,
  parseExplorerUrl,
  snapshotParamsOf,
  suggestedQuery,
  validateValues,
  valuesKey,
  valuesOf,
} from "@/features/time-machine/params";
import { snapshotPath } from "@/lib/api/snapshot";

const DEMO_HREF =
  "/time-machine?as_of=2020-06-05T09:30&tickers=AAPL,TSLA&series=UNRATE,FEDFUNDS";

function searchParamsOf(href: string): Record<string, string> {
  return Object.fromEntries(new URL(href, "http://localhost").searchParams);
}

describe("explorerHref", () => {
  it("writes the §2.3 example as a readable link", () => {
    expect(explorerHref(demoQuery)).toBe(DEMO_HREF);
  });

  it("leaves out an empty list", () => {
    expect(explorerHref({ ...demoQuery, tickers: [] })).toBe(
      "/time-machine?as_of=2020-06-05T09:30&series=UNRATE,FEDFUNDS",
    );
  });

  it("round-trips through parseExplorerUrl", () => {
    const parsed = parseExplorerUrl(searchParamsOf(explorerHref(demoQuery)));
    expect(parsed.state).toBe("ready");
    expect(parsed.query).toEqual(demoQuery);
  });

  it("reads the encoded form a GET form submits", () => {
    const parsed = parseExplorerUrl(
      searchParamsOf("/time-machine?as_of=2020-06-05T09%3A30&tickers=AAPL%2CTSLA&series=UNRATE%2CFEDFUNDS"),
    );
    expect(parsed.query).toEqual(demoQuery);
  });
});

describe("snapshotParamsOf", () => {
  it("asks the API exactly the §2.3 question", () => {
    expect(snapshotPath(snapshotParamsOf(demoQuery))).toBe(
      "/v1/snapshot?as_of=2020-06-05T09:30&tickers=AAPL,TSLA&series=UNRATE,FEDFUNDS",
    );
  });
});

describe("parseEntries", () => {
  it("reads a list the way the API does", () => {
    expect(parseEntries(" tsla, AAPL,aapl,,")).toEqual(["TSLA", "AAPL"]);
  });

  it("joins repeated keys, which the API would otherwise drop", () => {
    expect(parseEntries(["AAPL", "tsla,MSFT"])).toEqual(["AAPL", "TSLA", "MSFT"]);
  });

  it("is empty when the parameter is missing", () => {
    expect(parseEntries(undefined)).toEqual([]);
  });
});

describe("parseExplorerUrl", () => {
  it("reads a bare date as 09:30 ET", () => {
    const parsed = parseExplorerUrl({
      as_of: "2020-06-05",
      tickers: "AAPL,TSLA",
      series: "UNRATE,FEDFUNDS",
    });
    expect(parsed.query).toEqual(demoQuery);
    expect(parsed.values).toEqual({
      date: "2020-06-05",
      time: "09:30",
      tickers: ["AAPL", "TSLA"],
      series: ["UNRATE", "FEDFUNDS"],
    });
  });

  it("drops seconds, which moves the moment earlier, never later", () => {
    const parsed = parseExplorerUrl({ as_of: "2020-06-05T08:30:45", series: "UNRATE" });
    expect(parsed.values.time).toBe("08:30");
    expect(parsed.query?.moment.minute).toBe(30);
  });

  it("is blank with no parameters", () => {
    const parsed = parseExplorerUrl({});
    expect(parsed.state).toBe("blank");
    expect(parsed.values).toEqual({ date: "", time: "09:30", tickers: [], series: [] });
    expect(parsed.issues).toEqual({});
  });

  it("is moment-only when a link holds just a moment", () => {
    const parsed = parseExplorerUrl({ as_of: "2020-06-05T09:30" });
    expect(parsed.state).toBe("moment-only");
    expect(parsed.moment).toEqual(demoQuery.moment);
    expect(parsed.query).toBeNull();
  });

  it("asks for a moment when a link has companies but no as_of", () => {
    const parsed = parseExplorerUrl({ tickers: "AAPL" });
    expect(parsed.state).toBe("invalid");
    expect(parsed.issues.as_of).toBe("Pick a date for the knowledge time.");
    expect(parsed.values.tickers).toEqual(["AAPL"]);
  });

  it.each([
    ["2020-06-05T13:30Z", /has a time zone/],
    ["2020-06-05T09:30-04:00", /has a time zone/],
    ["2020-02-30", /isn't a knowledge time/],
    ["banana", /isn't a knowledge time/],
  ])("flags as_of=%s and runs nothing", (asOf, message) => {
    const parsed = parseExplorerUrl({ as_of: asOf, tickers: "AAPL" });
    expect(parsed.state).toBe("invalid");
    expect(parsed.issues.as_of).toMatch(message);
    expect(parsed.query).toBeNull();
  });

  it("flags more than 10 companies and runs nothing", () => {
    const tickers = Array.from({ length: MAX_ENTRIES + 1 }, (_, i) => `T${i}`).join(",");
    const parsed = parseExplorerUrl({ as_of: "2020-06-05", tickers });
    expect(parsed.issues.tickers).toBe("Choose at most 10 companies (there are 11).");
    expect(parsed.query).toBeNull();
  });

  it("flags characters a ticker or series ID can't have", () => {
    const parsed = parseExplorerUrl({ as_of: "2020-06-05", tickers: "AAPL;X,BRK.B", series: "UN RATE" });
    expect(parsed.issues.tickers).toMatch(/^“AAPL;X” isn't a ticker/);
    expect(parsed.issues.series).toMatch(/^“UN RATE” isn't a series ID/);
  });
});

describe("validateValues", () => {
  const values = valuesOf(demoQuery);

  it("turns valid values into the query", () => {
    expect(validateValues(values)).toEqual({ errors: {}, query: demoQuery });
  });

  it("reads a blank time as 09:30", () => {
    expect(validateValues({ ...values, time: "" }).query).toEqual(demoQuery);
  });

  it("asks for a date", () => {
    expect(validateValues({ ...values, date: "" }).errors).toEqual({ as_of: "Pick a date." });
  });

  it("asks for a company or a series, under companies as the API does", () => {
    expect(validateValues({ ...values, tickers: [], series: [] }).errors).toEqual({
      tickers: "Choose at least one company or series.",
    });
  });

  it("limits each list to 10", () => {
    const series = Array.from({ length: 11 }, (_, i) => `S${i}`);
    expect(validateValues({ ...values, series }).errors.series).toBe(
      "Choose at most 10 series (there are 11).",
    );
  });
});

describe("valuesKey", () => {
  it("is the same for the same view, where a blank time is 09:30", () => {
    expect(valuesKey({ ...valuesOf(demoQuery), time: "" })).toBe(valuesKey(valuesOf(demoQuery)));
  });

  it("matches what the URL parses to", () => {
    const parsed = parseExplorerUrl({ as_of: "2020-06-05", tickers: "aapl, tsla", series: "UNRATE,FEDFUNDS" });
    expect(valuesKey(parsed.values)).toBe(valuesKey(valuesOf(demoQuery)));
  });

  it("changes when the order changes, since results keep the order given", () => {
    expect(valuesKey({ ...valuesOf(demoQuery), tickers: ["TSLA", "AAPL"] })).not.toBe(
      valuesKey(valuesOf(demoQuery)),
    );
  });
});

describe("fieldErrorsFromFailure", () => {
  it("maps a 422's details onto fields", () => {
    const message =
      "2:30 AM on March 8, 2020 never happened in New York: clocks jumped from 2:00 to 3:00 AM. Add an offset, or choose another time.";
    expect(
      fieldErrorsFromFailure({
        kind: "response",
        status: 422,
        code: "invalid_request",
        message,
        details: [{ field: "as_of", message }],
      }),
    ).toEqual({ as_of: message });
  });

  it("keeps the first message when the API repeats a field", () => {
    expect(
      fieldErrorsFromFailure({
        kind: "response",
        status: 422,
        code: "invalid_request",
        message: "as_of is required. as_of is required.",
        details: [
          { field: "as_of", message: "as_of is required." },
          { field: "as_of", message: "as_of is required." },
        ],
      }),
    ).toEqual({ as_of: "as_of is required." });
  });

  it("puts an unknown ticker or series on its list", () => {
    const meta = "No security in our data used the ticker META as of June 5, 2020, 9:30 AM ET.";
    expect(
      fieldErrorsFromFailure({ kind: "response", status: 404, code: "unknown_ticker", message: meta, details: [] }),
    ).toEqual({ tickers: meta });
    const dgs10 = "DGS10 isn't a series in our catalog.";
    expect(
      fieldErrorsFromFailure({ kind: "response", status: 404, code: "unknown_series", message: dgs10, details: [] }),
    ).toEqual({ series: dgs10 });
  });

  it("leaves other failures off the fields", () => {
    expect(fieldErrorsFromFailure({ kind: "unreachable" })).toEqual({});
    expect(fieldErrorsFromFailure({ kind: "timeout" })).toEqual({});
    expect(
      fieldErrorsFromFailure({ kind: "response", status: 500, code: "internal_error", message: "x", details: [] }),
    ).toEqual({});
  });
});

describe("catalogAsOf", () => {
  it("reads the pickers' catalogs at 09:30 on the date, even for a time in the DST gap", () => {
    const inTheGap = parseExplorerUrl({ as_of: "2020-03-08T02:30", tickers: "AAPL" }).moment;
    expect(inTheGap && catalogAsOf(inTheGap)).toBe("2020-03-08T09:30");
  });
});

describe("suggestedQuery", () => {
  it("uses the §2.3 selection on its moment, and the starter selection elsewhere", () => {
    expect(suggestedQuery(demoQuery.moment)).toEqual(demoQuery);
    const moment = { year: 1995, month: 3, day: 1, hour: 9, minute: 30 };
    expect(suggestedQuery(moment)).toEqual({ moment, tickers: ["AAPL"], series: ["UNRATE", "FEDFUNDS"] });
  });
});
