import { describe, expect, it } from "vitest";

import { auditSections, edgarIndexUrl, knownBy, newestFilings } from "@/features/backtests/audit";
import { auditJune, membersJune } from "@/features/backtests/fixtures/backtest-results";
import type { AuditView, BacktestMember } from "@/lib/api/types";

const VIEWS: AuditView[] = auditJune.views;
// The documented members, as their route's type: the literal's `{}` reasons widen otherwise.
const MEMBERS = membersJune.members as BacktestMember[];

describe("auditSections", () => {
  it("shows what the June 1, 2020 decision could see, all known by 9:30 AM ET", () => {
    const [decision] = auditSections(VIEWS, MEMBERS);

    expect(decision).toMatchObject({
      purpose: "decision",
      title: "What the decision could see",
      knowledgeTime: "Jun 1, 2020, 9:30 AM ET",
      rows: 17732,
      allKnown: true,
    });
    // What the signals read comes first: the financials before the macro release.
    expect(decision.tables.map((t) => [t.title, t.rows, t.earliest, t.newest, t.known])).toEqual([
      ["Reported financials", 8249, "Jul 22, 2009, 12:32 PM ET", "May 26, 2020, 7:59 PM ET", true],
      ["Macro releases", 1, "May 1, 2020, 4:15 PM ET", "May 1, 2020, 4:15 PM ET", true],
    ]);
  });

  it("names Apple's facts and the newest filing they came from (eval task T5)", () => {
    const [decision] = auditSections(VIEWS, MEMBERS);
    const [apple] = decision.tables[0].groups;

    expect(apple).toEqual({
      key: "320193",
      label: "Apple Inc. (AAPL)",
      detail: "CIK 320193",
      isKey: false,
      rows: 248,
      newest: "Apr 30, 2020, 6:03 PM ET",
      known: true,
      source: {
        text: "0000320193-20-000052",
        href: "https://www.sec.gov/Archives/edgar/data/320193/000032019320000052/0000320193-20-000052-index.htm",
      },
    });
  });

  it("falls back to the CIK without a members record, and leaves other keys as they are", () => {
    const [decision] = auditSections(VIEWS, null);
    expect(decision.tables[0].groups[0]).toMatchObject({ label: "CIK 320193", detail: null });
    expect(decision.tables[1].groups[0]).toMatchObject({
      label: "TB3MS",
      isKey: true,
      source: { text: "TB3MS vintage 2020-05-01", href: null },
    });
  });

  it("never shows a record dated after the knowledge time as known", () => {
    // A row made public at 9:31, a minute after the decision: a leak the page must show.
    const [view] = VIEWS;
    const leaked: AuditView = {
      ...view,
      tables: [
        {
          ...view.tables[1],
          latest_available_at: "2020-06-01T09:31:00-04:00",
          groups: [
            { ...view.tables[1].groups[0], latest_available_at: "2020-06-01T09:31:00-04:00" },
          ],
        },
      ],
    };

    const [section] = auditSections([leaked], MEMBERS);

    expect(section.allKnown).toBe(false);
    expect(section.tables[0].known).toBe(false);
    expect(section.tables[0].groups[0].known).toBe(false);
  });
});

describe("knownBy", () => {
  it("compares instants, offsets and microseconds included", () => {
    expect(knownBy("2020-06-01T09:30:00-04:00", "2020-06-01T13:30:00Z")).toBe(true);
    expect(knownBy("2020-06-01T09:30:00.000001-04:00", "2020-06-01T09:30:00-04:00")).toBe(false);
  });

  it("doesn't count a time it can't read as known", () => {
    expect(knownBy("…", "2020-06-01T09:30:00-04:00")).toBe(false);
  });
});

describe("edgarIndexUrl", () => {
  it("links an accession number to its filing's index on EDGAR", () => {
    expect(edgarIndexUrl(320193, "0000320193-20-000052")).toBe(
      "https://www.sec.gov/Archives/edgar/data/320193/000032019320000052/0000320193-20-000052-index.htm",
    );
  });

  it("links nothing that isn't an accession number", () => {
    expect(edgarIndexUrl(320193, "tiingo AAPL 2020-05-29")).toBeNull();
  });
});

describe("newestFilings", () => {
  it("names the newest filing the decision read for each company, by CIK", () => {
    const filings = newestFilings(auditSections(VIEWS, MEMBERS));
    expect([...filings.keys()]).toEqual(["320193"]);
    expect(filings.get("320193")).toMatchObject({
      newest: "Apr 30, 2020, 6:03 PM ET",
      source: { text: "0000320193-20-000052" },
    });
  });

  it("has none without a decision view", () => {
    expect(newestFilings([])).toEqual(new Map());
  });
});
