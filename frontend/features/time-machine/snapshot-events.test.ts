import { describe, expect, it } from "vitest";

import { june5Snapshot } from "@/features/time-machine/fixtures/snapshot-june-5-2020";
import type { MomentEvent } from "@/features/time-machine/moment-event";
import { buildSnapshotView, type EntityHorizon } from "@/features/time-machine/snapshot-events";
import type { CatalogSeries, Snapshot, V1Response } from "@/lib/api/types";
import { formatEtShortDate, formatEtTime, toAsOfParam } from "@/lib/time";

/** A fresh, writable copy of the API's §2.3 example. */
function snapshot(): V1Response<Snapshot> {
  return structuredClone(june5Snapshot) as V1Response<Snapshot>;
}

function entity(entities: EntityHorizon[], code: string): EntityHorizon {
  const found = entities.find((item) => item.code === code);
  if (!found) throw new Error(`No card for ${code}`);
  return found;
}

function event(horizon: EntityHorizon, id: string): MomentEvent {
  const found = horizon.events.find((item) => item.id === id);
  if (!found) throw new Error(`No event ${id} in ${horizon.key}`);
  return found;
}

/** The time as the horizon prints it, such as "Apr 30, 2020, 6:03 PM ET". */
function shownTime(item: MomentEvent): string {
  return `${formatEtShortDate(item.at)}${item.timeNote ? ` · ${item.timeNote}` : `, ${formatEtTime(item.at)}`}`;
}

describe("buildSnapshotView on the §2.3 example (doc/reference/time-model.md, June 5, 2020)", () => {
  const view = buildSnapshotView(snapshot());
  const aapl = entity(view.companies, "AAPL");
  const tsla = entity(view.companies, "TSLA");
  const unrate = entity(view.series, "UNRATE");
  const fedfunds = entity(view.series, "FEDFUNDS");

  it("echoes the knowledge time and keeps the order asked for", () => {
    expect(view.knowledgeTime).toEqual({ year: 2020, month: 6, day: 5, hour: 9, minute: 30 });
    expect(view.companies.map((item) => item.code)).toEqual(["AAPL", "TSLA"]);
    expect(view.series.map((item) => item.code)).toEqual(["UNRATE", "FEDFUNDS"]);
    expect(view.hidden).toBe(0);
  });

  it("knows AAPL's bars through the June 4 close", () => {
    const close = event(aapl, "company-AAPL:bar:2020-06-04");
    expect(close.known).toBe(true);
    expect(shownTime(close)).toBe("Jun 4, 2020, 4:00 PM ET");
    expect(close.label).toBe("Close on Jun 4, 2020");
    expect(close.detail).toMatch(/^Price withheld on this server/);
  });

  it("doesn't know the June 5 close", () => {
    const close = event(aapl, "company-AAPL:next-bar:2020-06-05");
    expect(close.known).toBe(false);
    expect(shownTime(close)).toBe("Jun 5, 2020, 4:00 PM ET");
  });

  it("knows May 2020's unemployment rate, first printed at 13.3% that morning", () => {
    const may = event(unrate, "series-UNRATE:latest:2020-06-05");
    expect(may.known).toBe(true);
    expect(shownTime(may)).toBe("Jun 5, 2020, 8:30 AM ET");
    expect(may.label).toBe("May 2020: 13.3%");
    expect(may.link?.href).toBe("https://alfred.stlouisfed.org/series?seid=UNRATE");
  });

  it("doesn't know the later revision to 13.2%", () => {
    const revision = unrate.events.find((item) => !item.known);
    expect(revision?.label).toBe("May 2020 revised to 13.2% (was 13.3%)");
    expect(revision && shownTime(revision)).toBe("Jan 7, 2022, 8:30 AM ET");
  });

  it("knows Apple's 10-Q for the quarter ended March 28 from its acceptance time", () => {
    const tenQ = event(aapl, "company-AAPL:filing:0000320193-20-000052");
    expect(tenQ.known).toBe(true);
    expect(shownTime(tenQ)).toBe("Apr 30, 2020, 6:03 PM ET");
    expect(tenQ.label).toBe("10-Q for the quarter ended Mar 28, 2020");
    expect(tenQ.detail).toBe(
      "Usable from its EDGAR acceptance time, not its filing date (May 1, 2020).",
    );
    expect(tenQ.link).toEqual({
      href: "https://www.sec.gov/Archives/edgar/data/320193/000032019320000052/a10-qq220203282020.htm",
      label: "EDGAR 0000320193-20-000052",
    });
  });

  it("knows the fiscal Q2 2020 revenue that 10-Q reported", () => {
    const revenue = aapl.events.find((item) => item.known && item.label.startsWith("Revenue"));
    expect(revenue?.label).toBe("Revenue, fiscal Q2 2020: $58,313 million");
    expect(revenue && shownTime(revenue)).toBe("Apr 30, 2020, 6:03 PM ET");
  });

  it("doesn't know the same revenue as re-reported in the fiscal 2020 10-K", () => {
    const versions = aapl.events.filter((item) => !item.known && item.label.startsWith("Revenue"));
    expect(versions.map((item) => item.label)).toEqual([
      "Revenue, fiscal Q2 2020, re-reported: $58,313 million",
      "Revenue, fiscal Q2 2020, re-reported: $58,313 million",
    ]);
    expect(shownTime(versions[0])).toBe("Oct 29, 2020, 6:06 PM ET");
  });

  it("doesn't know Apple's 10-Q for the quarter ended June 27", () => {
    const tenQ = event(aapl, "company-AAPL:filing:0000320193-20-000062");
    expect(tenQ.known).toBe(false);
    expect(tenQ.label).toBe("10-Q for the quarter ended Jun 27, 2020");
    expect(shownTime(tenQ)).toBe("Jul 30, 2020, 7:29 PM ET");
  });

  it("doesn't know an amendment accepted after June 5, and names what it amends", () => {
    const amendment = event(aapl, "company-AAPL:amendment:0000320193-20-900001");
    expect(amendment.known).toBe(false);
    expect(amendment.label).toBe("10-Q/A amending the 10-Q for the quarter ended Mar 28, 2020");
    expect(shownTime(amendment)).toBe("Jun 10, 2020, 4:00 PM ET");
  });

  it("knows the Fed data published by that morning", () => {
    const may = event(fedfunds, "series-FEDFUNDS:latest:2020-06-01");
    expect(may.known).toBe(true);
    expect(may.label).toBe("May 2020: 0.05%");
    expect(shownTime(may)).toBe("Jun 1, 2020, 4:15 PM ET");
    expect(fedfunds.events.filter((item) => !item.known)).toEqual([]);
    expect(fedfunds.emptyNotYetKnown).toBe("No later revision of this value in our data.");
  });

  it("doesn't know universe changes effective after June 5", () => {
    const joins = tsla.events.find((item) => !item.known);
    expect(joins?.label).toBe("Joins starter_large_caps");
    expect(joins && shownTime(joins)).toBe("Dec 21, 2020 · effective");
    expect(joins?.link?.href).toBe("https://press.spglobal.com/2020-11-16-Tesla-Set-to-Join-S-P-500");
  });

  it("puts every known event at or before T, and every other one after it", () => {
    const t = toAsOfParam(view.knowledgeTime);
    for (const item of [...view.companies, ...view.series].flatMap((horizon) => horizon.events)) {
      if (item.known) expect(toAsOfParam(item.at) <= t, item.id).toBe(true);
      else expect(toAsOfParam(item.at) > t, item.id).toBe(true);
    }
  });

  it("keeps each side in time order", () => {
    for (const horizon of [...view.companies, ...view.series]) {
      for (const known of [true, false]) {
        const times = horizon.events.filter((item) => item.known === known).map((item) => toAsOfParam(item.at));
        expect(times).toEqual([...times].sort());
      }
    }
  });

  it("flags a time our source didn't give", () => {
    const tenK = event(aapl, "company-AAPL:filing:0000912057-01-544436");
    expect(tenK.label).toBe("10-K405 for the fiscal year ended Sep 29, 2001");
    expect(shownTime(tenK)).toBe("Dec 21, 2001 · end of day, assumed");
    expect(tenK.caveat).toMatch(/no time of day/);
  });

  it("lists what a company had nothing of by T", () => {
    expect(tsla.missing).toEqual([
      "a closing price",
      "a 10-K",
      "a 10-Q",
      "an 8-K",
      "quarterly revenue",
    ]);
    expect(tsla.facts).toEqual(["CIK 1318605", "Not in a universe at T"]);
    expect(aapl.facts).toEqual(["CIK 320193", "In starter_large_caps at T"]);
  });

  it("reports withheld prices and the data version", () => {
    expect(view.pricesWithheld).toBe(true);
    expect(view.dataVersion).toBe("20261019T120000Z");
    expect(view.dataCut).toEqual({ year: 2026, month: 10, day: 19, hour: 8, minute: 0 });
    expect(view.afterDataCut).toBe(false);
  });
});

describe("buildSnapshotView keeps future records off the known side", () => {
  it("leaves out a 'known' record whose time is after T, and counts it", () => {
    const response = snapshot();
    const tenQ = response.data.known.companies[0].latest_filings["10-Q"];
    if (!tenQ) throw new Error("fixture changed");
    tenQ.available_at = "2020-07-30T19:29:09-04:00"; // after T, but listed as known

    const view = buildSnapshotView(response);
    const ids = view.companies[0].events.map((item) => item.id);
    expect(ids).not.toContain("company-AAPL:filing:0000320193-20-000052");
    expect(view.companies[0].events.filter((item) => item.known).every((item) => toAsOfParam(item.at) <= "2020-06-05T09:30")).toBe(true);
    expect(view.hidden).toBe(1);
  });

  it("leaves out a 'not yet known' record whose time is at or before T, and counts it", () => {
    const response = snapshot();
    response.data.not_yet_known.series[0].revisions[0].available_at = "2020-06-05T08:30:00-04:00";

    const view = buildSnapshotView(response);
    expect(view.series[0].events.filter((item) => !item.known)).toEqual([]);
    expect(view.hidden).toBe(1);
  });

  it("counts a record public exactly at T as known", () => {
    const response = snapshot();
    const fedfunds = response.data.known.series[1].latest;
    if (!fedfunds) throw new Error("fixture changed");
    fedfunds.available_at = "2020-06-05T09:30:00-04:00";

    const view = buildSnapshotView(response);
    expect(view.series[1].events[0]).toMatchObject({ known: true, label: "May 2020: 0.05%" });
    expect(view.hidden).toBe(0);
  });
});

describe("buildSnapshotView edge cases", () => {
  it("prints the close when the server serves prices", () => {
    const response = snapshot();
    const aapl = response.data.known.companies[0];
    aapl.prices_withheld = false;
    response.data.known.companies[1].prices_withheld = false;
    if (!aapl.latest_bar) throw new Error("fixture changed");
    aapl.latest_bar.close = 322.32;

    const view = buildSnapshotView(response);
    expect(view.pricesWithheld).toBe(false);
    expect(event(view.companies[0], "company-AAPL:bar:2020-06-04").label).toBe(
      "Close on Jun 4, 2020: $322.32",
    );
  });

  it("names a series with nothing published yet from the catalog", () => {
    const response = snapshot();
    response.data.known.series[0].latest = null;
    response.data.not_yet_known.series[0] = { series_id: "UNRATE", period: null, revisions: [] };
    const catalog: CatalogSeries[] = [
      {
        series_id: "UNRATE",
        title: "Unemployment Rate",
        units: "Percent",
        frequency: "Monthly",
        seasonal_adjustment: "Seasonally Adjusted",
        release: "Employment Situation",
        observations: null,
        vintages: null,
      },
    ];

    const unrate = buildSnapshotView(response, catalog).series[0];
    expect(unrate.name).toBe("Unemployment Rate");
    expect(unrate.facts).toEqual(["Percent", "Monthly", "Seasonally Adjusted", "Employment Situation"]);
    expect(unrate.events).toEqual([]);
    expect(unrate.emptyKnown).toBe("No value had been published by T.");
  });

  it("pairs a company's two halves by ticker, whatever the order", () => {
    const response = snapshot();
    response.data.not_yet_known.companies.reverse();

    const view = buildSnapshotView(response);
    expect(entity(view.companies, "TSLA").events.map((item) => item.label)).toContain(
      "Joins starter_large_caps",
    );
    expect(view.hidden).toBe(0);
  });

  it("notices a moment after the data version was cut", () => {
    const response: V1Response<Snapshot> = {
      ...snapshot(),
      knowledge_time: "2030-01-02T09:30:00-05:00",
      data: {
        known: { companies: [], series: [] },
        not_yet_known: { companies: [], series: [] },
      },
    };
    expect(buildSnapshotView(response).afterDataCut).toBe(true);
  });
});
