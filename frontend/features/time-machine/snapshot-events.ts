// Turns a snapshot (GET /v1/snapshot) into what the Time Machine draws: one knowledge
// horizon per company and per series. Pure, so snapshot-events.test.ts can check it.
//
// The side of T each record lands on is decided here, from the record's own
// `available_at` and the response's `knowledge_time`, not from the section the API put
// it in. A record whose time contradicts its section is left out and counted in
// `hidden`, so a future-dated record can never show as known, even if the API
// misplaced one.

import type { MomentEvent } from "@/features/time-machine/moment-event";
import type {
  CatalogSeries,
  Filing,
  FilingsByForm,
  Fundamental,
  MacroObservation,
  Membership,
  NextBar,
  PriceBar,
  Snapshot,
  SnapshotCompanyKnown,
  SnapshotCompanyNotYetKnown,
  UniverseChange,
  V1Response,
} from "@/lib/api/types";
import { formatMacroValue, formatNumber, formatUsd, formatUsdMillions } from "@/lib/format";
import {
  etDateTimeOf,
  formatEtShortDate,
  formatPeriod,
  instantOf,
  parseIsoDate,
  toEtDateTime,
  type EtDateTime,
} from "@/lib/time";

/** One company or series, ready for a card with a knowledge horizon. */
export type EntityHorizon = {
  /** Unique on the page, such as `company-AAPL`; used in ids. */
  key: string;
  kind: "company" | "series";
  /** The ticker or the series ID. */
  code: string;
  /** The company's name or the series' title. */
  name: string;
  /** Short facts for the card's header, such as "CIK 320193". */
  facts: string[];
  events: MomentEvent[];
  emptyKnown: string;
  emptyNotYetKnown: string;
  /** Records our data didn't have by T, such as "a 10-K". */
  missing: string[];
};

export type SnapshotView = {
  knowledgeTime: EtDateTime;
  dataVersion: string | null;
  /** When the data version was cut, New York time, if its name says. */
  dataCut: EtDateTime | null;
  /** T is after the data version's cut, so nothing can show as not yet known. */
  afterDataCut: boolean;
  /** The server withholds raw prices (D2): closes keep their dates but lose their prices. */
  pricesWithheld: boolean;
  companies: EntityHorizon[];
  series: EntityHorizon[];
  /** Records left out because their time contradicts their section. Should be 0. */
  hidden: number;
};

const FORMS = ["10-K", "10-Q", "8-K"] as const;
type FormFamily = (typeof FORMS)[number];

const MISSING_FORM: Record<FormFamily, string> = {
  "10-K": "a 10-K",
  "10-Q": "a 10-Q",
  "8-K": "an 8-K",
};

const DATA_VERSION_PATTERN = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/;

/** Builds the page's view of a snapshot. `seriesCatalog` names series with no value yet. */
export function buildSnapshotView(
  response: V1Response<Snapshot>,
  seriesCatalog: readonly CatalogSeries[] = [],
): SnapshotView {
  const knowledgeTime = etDateTimeOf(response.knowledge_time);
  const t = instantOf(response.knowledge_time);
  if (!knowledgeTime || Number.isNaN(t)) {
    throw new Error(`Unexpected knowledge_time from the API: ${response.knowledge_time}`);
  }

  const cut = dataVersionInstant(response.data_version);
  const { known, not_yet_known: notYetKnown } = response.data;
  let hidden = 0;

  const companies = known.companies.map((company, index) => {
    const later =
      notYetKnown.companies[index]?.ticker === company.ticker
        ? notYetKnown.companies[index]
        : notYetKnown.companies.find((entry) => entry.ticker === company.ticker);
    const built = companyHorizon(company, later, t);
    hidden += built.hidden;
    return built.horizon;
  });

  const series = known.series.map((entry, index) => {
    const later =
      notYetKnown.series[index]?.series_id === entry.series_id
        ? notYetKnown.series[index]
        : notYetKnown.series.find((item) => item.series_id === entry.series_id);
    const catalog = seriesCatalog.find((item) => item.series_id === entry.series_id);
    const built = seriesHorizon(entry.series_id, entry.latest, later?.revisions ?? [], catalog, t);
    hidden += built.hidden;
    return built.horizon;
  });

  return {
    knowledgeTime,
    dataVersion: response.data_version,
    dataCut: cut === null ? null : toEtDateTime(new Date(cut)),
    afterDataCut: cut !== null && t > cut,
    pricesWithheld: known.companies.some((company) => company.prices_withheld),
    companies,
    series,
    hidden,
  };
}

/** Collects one entity's events, keeping only records whose time matches their side. */
class Timeline {
  private entries: { event: MomentEvent; instant: number; order: number }[] = [];
  hidden = 0;

  constructor(private readonly t: number) {}

  /** Adds a record the API listed as known (`expectKnown`) or not yet known. */
  add(expectKnown: boolean, availableAt: string, event: Omit<MomentEvent, "at" | "known">) {
    const at = etDateTimeOf(availableAt);
    const instant = instantOf(availableAt);
    // Inclusive: a record public exactly at T is known at T (doc/time-model.md).
    const known = instant <= this.t;
    if (!at || Number.isNaN(instant) || known !== expectKnown) {
      this.hidden += 1;
      return;
    }
    this.entries.push({ event: { ...event, at, known }, instant, order: this.entries.length });
  }

  /** The events in time order, ties in the order they were added. */
  events(): MomentEvent[] {
    return [...this.entries]
      .sort((a, b) => a.instant - b.instant || a.order - b.order)
      .map((entry) => entry.event);
  }
}

function companyHorizon(
  company: SnapshotCompanyKnown,
  later: SnapshotCompanyNotYetKnown | undefined,
  t: number,
): { horizon: EntityHorizon; hidden: number } {
  const key = `company-${company.ticker}`;
  const timeline = new Timeline(t);
  const missing: string[] = [];

  // Known at T.
  if (company.latest_bar) addLatestBar(timeline, key, company.latest_bar, company.prices_withheld);
  else missing.push("a closing price");

  for (const form of FORMS) {
    const filing = company.latest_filings[form];
    if (filing) addFiling(timeline, true, key, form, filing);
    else missing.push(MISSING_FORM[form]);
  }

  if (company.latest_revenue) addRevenue(timeline, true, key, company.latest_revenue, null, 0);
  else missing.push("quarterly revenue");

  company.universes.forEach((membership) => addMembership(timeline, key, membership));

  // Not yet known at T.
  if (later) {
    if (later.next_bar) addNextBar(timeline, key, later.next_bar);
    for (const form of FORMS) {
      const filing = later.next_filings[form];
      if (filing) addFiling(timeline, false, key, form, filing);
    }
    later.later_amendments.forEach((amendment) =>
      addAmendment(timeline, key, amendment, company.latest_filings),
    );
    let previous = company.latest_revenue?.value ?? null;
    later.later_revenue.forEach((version, index) => {
      addRevenue(timeline, false, key, version, previous, index + 1);
      previous = version.value;
    });
    later.universe_changes.forEach((change, index) =>
      addUniverseChange(timeline, key, change, index),
    );
  }

  const facts: string[] = [];
  if (company.cik !== null) facts.push(`CIK ${company.cik}`);
  facts.push(
    company.universes.length > 0
      ? `In ${company.universes.map((membership) => membership.universe).join(", ")} at T`
      : "Not in a universe at T",
  );
  if (later && later.later_amendments.length >= 10) facts.push("First 10 later amendments shown");

  return {
    horizon: {
      key,
      kind: "company",
      code: company.ticker,
      name: company.company_name,
      facts,
      events: timeline.events(),
      emptyKnown: "Nothing about this company in our data was public by T.",
      emptyNotYetKnown: "Nothing about this company in our data became public after T.",
      missing,
    },
    hidden: timeline.hidden,
  };
}

function seriesHorizon(
  seriesId: string,
  latest: MacroObservation | null,
  revisions: MacroObservation[],
  catalog: CatalogSeries | undefined,
  t: number,
): { horizon: EntityHorizon; hidden: number } {
  const key = `series-${seriesId}`;
  const timeline = new Timeline(t);
  const about = latest ?? catalog;

  if (latest) {
    timeline.add(true, latest.available_at, {
      id: `${key}:latest:${latest.vintage_date}`,
      label: `${formatPeriod(latest.period, latest.frequency)}: ${formatMacroValue(latest.value, latest.units)}`,
      detail:
        latest.value === null
          ? "Published as missing."
          : `${latest.release} release, vintage of ${shortDate(latest.vintage_date)}.`,
      ...provenance(latest),
      link: alfredLink(seriesId),
    });
  }

  let previous = latest?.value ?? null;
  revisions.forEach((revision, index) => {
    const value = formatMacroValue(revision.value, revision.units);
    const period = formatPeriod(revision.period, revision.frequency);
    const changed = revision.value !== previous;
    timeline.add(false, revision.available_at, {
      id: `${key}:revision:${index}:${revision.vintage_date}`,
      label: changed
        ? `${period} revised to ${value}${previous === null ? "" : ` (was ${formatMacroValue(previous, revision.units)})`}`
        : `${period} published again at ${value}`,
      detail: `${revision.release} release, vintage of ${shortDate(revision.vintage_date)}.`,
      ...provenance(revision),
    });
    previous = revision.value;
  });

  const facts = about
    ? [about.units, about.frequency, about.seasonal_adjustment, about.release].filter(Boolean)
    : [];

  return {
    horizon: {
      key,
      kind: "series",
      code: seriesId,
      name: about?.title ?? seriesId,
      facts,
      events: timeline.events(),
      emptyKnown: "No value had been published by T.",
      emptyNotYetKnown: latest
        ? "No later revision of this value in our data."
        : "Later releases aren't listed: only revisions of a value known at T are.",
      missing: [],
    },
    hidden: timeline.hidden,
  };
}

function addLatestBar(timeline: Timeline, key: string, bar: PriceBar, withheld: boolean) {
  const session = shortDate(bar.session_date);
  const price = bar.close === null ? null : formatUsd(bar.close);
  timeline.add(true, bar.available_at, {
    id: `${key}:bar:${bar.session_date}`,
    label: price ? `Close on ${session}: ${price}` : `Close on ${session}`,
    detail: price
      ? "A daily bar is known once its session closes."
      : withheld
        ? "Price withheld on this server. The close became known when the session ended."
        : "No closing price in our data for this session.",
    ...provenance(bar),
  });
}

function addNextBar(timeline: Timeline, key: string, bar: NextBar) {
  timeline.add(false, bar.available_at, {
    id: `${key}:next-bar:${bar.session_date}`,
    label: `Close on ${shortDate(bar.session_date)}`,
    detail: "Not known until the session closes.",
  });
}

function addFiling(
  timeline: Timeline,
  expectKnown: boolean,
  key: string,
  family: FormFamily,
  filing: Filing,
) {
  const acceptedOn = filing.available_at.slice(0, 10);
  const filedLater = filing.filing_date !== acceptedOn;
  timeline.add(expectKnown, filing.available_at, {
    id: `${key}:filing:${filing.accession_number}`,
    label: filingLabel(family, filing),
    detail: expectKnown
      ? filedLater
        ? `Usable from its EDGAR acceptance time, not its filing date (${shortDate(filing.filing_date)}).`
        : "Usable from its EDGAR acceptance time."
      : "Not public until EDGAR accepted it.",
    ...provenance(filing),
    link: edgarLink(filing),
  });
}

function addAmendment(
  timeline: Timeline,
  key: string,
  amendment: Filing,
  knownFilings: FilingsByForm,
) {
  const original = FORMS.map((form) => [form, knownFilings[form]] as const).find(
    ([, filing]) => filing !== null && filing.accession_number === amendment.amends,
  );
  const amends = original
    ? ` amending the ${filingLabel(original[0], original[1]!)}`
    : amendment.amends
      ? ` amending ${amendment.amends}`
      : "";
  timeline.add(false, amendment.available_at, {
    id: `${key}:amendment:${amendment.accession_number}`,
    label: `${amendment.form}${amends}`,
    detail: "An amendment counts only from its own acceptance time.",
    ...provenance(amendment),
    link: edgarLink(amendment),
  });
}

function addRevenue(
  timeline: Timeline,
  expectKnown: boolean,
  key: string,
  revenue: Fundamental,
  previous: number | null,
  version: number,
) {
  const quarter =
    revenue.fiscal_period && revenue.fiscal_year
      ? `fiscal ${revenue.fiscal_period} ${revenue.fiscal_year}`
      : `the quarter ended ${shortDate(revenue.period_end)}`;
  const amount =
    revenue.unit === "USD"
      ? formatUsdMillions(revenue.value)
      : `${formatNumber(revenue.value)} ${revenue.unit}`;
  const filings = revenue.accession_numbers.join(", ");
  const source = revenue.derived
    ? `Derived from the fiscal year's total and its first three quarters (${filings}).`
    : `As reported in ${filings}.`;

  let label = `Revenue, ${quarter}: ${amount}`;
  if (!expectKnown) {
    const was =
      previous === null
        ? ""
        : revenue.unit === "USD"
          ? formatUsdMillions(previous)
          : `${formatNumber(previous)} ${revenue.unit}`;
    label =
      previous === null || previous === revenue.value
        ? `Revenue, ${quarter}, re-reported: ${amount}`
        : `Revenue, ${quarter}, restated to ${amount} (was ${was})`;
  }

  timeline.add(expectKnown, revenue.available_at, {
    id: `${key}:revenue:${version}:${revenue.available_at}`,
    label,
    detail: source,
    ...provenance(revenue),
  });
}

function addMembership(timeline: Timeline, key: string, membership: Membership) {
  timeline.add(true, membership.available_at, {
    id: `${key}:universe:${membership.universe}:${membership.added}`,
    timeNote: "effective",
    label: `Member of ${membership.universe}`,
    detail: "Membership counts from its effective date, never earlier.",
    ...provenance(membership),
    link: sourceLink(membership.source_ref),
  });
}

function addUniverseChange(timeline: Timeline, key: string, change: UniverseChange, index: number) {
  timeline.add(false, change.available_at, {
    id: `${key}:universe-change:${index}:${change.universe}:${change.effective}`,
    timeNote: "effective",
    label: `${change.change === "joins" ? "Joins" : "Leaves"} ${change.universe}`,
    detail: "A change counts from its effective date, never earlier.",
    ...provenance(change),
    link: sourceLink(change.source_ref),
  });
}

function filingLabel(family: FormFamily, filing: Filing): string {
  const period = filing.period_of_report ? parseIsoDate(filing.period_of_report) : null;
  const periodText = period ? formatEtShortDate(period) : null;
  if (family === "10-K") {
    return periodText ? `${filing.form} for the fiscal year ended ${periodText}` : `${filing.form} annual report`;
  }
  if (family === "10-Q") {
    return periodText ? `${filing.form} for the quarter ended ${periodText}` : `${filing.form} quarterly report`;
  }
  return periodText ? `${filing.form} current report, event of ${periodText}` : `${filing.form} current report`;
}

/** A caveat and an untimed label for records whose time is a conservative default. */
function provenance(record: { available_at: string; time_assumed: boolean }): {
  timeNote?: string;
  caveat?: string;
} {
  if (!record.time_assumed) return {};
  const at = etDateTimeOf(record.available_at);
  if (at && at.hour === 23 && at.minute === 59) {
    return {
      timeNote: "end of day, assumed",
      caveat: "Our source gives no time of day, so this counts from the end of that day.",
    };
  }
  return { caveat: "Our source gives no exact time, so this time is a conservative estimate." };
}

function edgarLink(filing: Filing): MomentEvent["link"] {
  return {
    href: filing.document_url ?? filing.index_url,
    label: `EDGAR ${filing.accession_number}`,
  };
}

function sourceLink(sourceRef: string): MomentEvent["link"] {
  return sourceRef.startsWith("https://") ? { href: sourceRef, label: "Source" } : undefined;
}

function alfredLink(seriesId: string): MomentEvent["link"] {
  return {
    href: `https://alfred.stlouisfed.org/series?seid=${encodeURIComponent(seriesId)}`,
    label: "Vintages on ALFRED",
  };
}

function shortDate(date: string): string {
  const parsed = parseIsoDate(date);
  return parsed ? formatEtShortDate(parsed) : date;
}

/** The instant a data version was cut, from its name, such as `20261101T202624Z`. */
function dataVersionInstant(version: string | null): number | null {
  const match = version ? DATA_VERSION_PATTERN.exec(version) : null;
  if (!match) return null;
  const [year, month, day, hour, minute, second] = match.slice(1).map(Number);
  return Date.UTC(year, month - 1, day, hour, minute, second);
}
