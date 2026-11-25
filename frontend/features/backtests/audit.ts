import { universeLabel } from "@/features/backtests/universes";
import type { AuditGroup, AuditTable, AuditView, BacktestMember } from "@/lib/api/types";
import {
  etDateTimeOf,
  formatEtShortDate,
  formatEtTime,
  instantOf,
  type EtDateTime,
} from "@/lib/time";

// The audit drill-down (S9.6): what each view a decision opened read, and when the newest
// of it became known, from GET /v1/backtests/{run_id}/audit?decision= (doc/reference/
// runs.md, "The audit"). Every row a view returns was public by its knowledge time T, or
// the view wouldn't have returned it; the page checks it anyway, so a leak would show.

export type AuditSource = { text: string; href: string | null };

export type AuditGroupRow = {
  key: string;
  /** "Apple Inc. (AAPL)" for a CIK a member had, otherwise the key itself. */
  label: string;
  /** "CIK 320193" under a company's name; null otherwise. */
  detail: string | null;
  /** Whether the label is an identifier, to set in mono. */
  isKey: boolean;
  rows: number;
  newest: string;
  known: boolean;
  source: AuditSource;
};

export type AuditTableRow = {
  table: string;
  title: string;
  description: string;
  rows: number;
  earliest: string;
  newest: string;
  /** True when its newest row was public at or before the view's knowledge time. */
  known: boolean;
  groups: AuditGroupRow[];
};

export type AuditSection = {
  purpose: AuditView["purpose"];
  title: string;
  description: string;
  /** The view's knowledge time T, in ET: as text, and as a moment for its label. */
  knowledgeTime: string;
  moment: EtDateTime | null;
  rows: number;
  /** True when every table's newest row was public by T. */
  allKnown: boolean;
  tables: AuditTableRow[];
};

const PURPOSES: Record<AuditView["purpose"], { title: string; description: string }> = {
  decision: {
    title: "What the decision could see",
    description:
      "Bound to the decision's time: the universe, every signal's inputs, the benchmark, and the risk-free rate.",
  },
  fill: {
    title: "What valued and filled the trades",
    description:
      "Bound to the close of the fill's session: the bars that valued the last period's holdings, and the prices this decision's trades filled at.",
  },
  end: {
    title: "What valued the last holdings",
    description: "Bound to the run's last close: the bars that valued its last period's holdings.",
  },
};

const TABLES: Record<string, { title: string; description: string }> = {
  price_bars: { title: "Daily price bars", description: "By security, under our ID for it" },
  xbrl_facts: {
    title: "Reported financials",
    description: "XBRL facts from SEC filings, by company",
  },
  macro_observations: {
    title: "Macro releases",
    description: "Each series' values as they were published",
  },
  corporate_actions: { title: "Splits and dividends", description: "By security" },
  securities: { title: "Security records", description: "Tickers, names, and identities" },
  universe_members: { title: "Universe membership", description: "Who was a member, by universe" },
};

/** The order tables are listed in: what the signals read first, then identities. */
const TABLE_ORDER = [
  "price_bars",
  "xbrl_facts",
  "macro_observations",
  "corporate_actions",
  "universe_members",
  "securities",
];

/** An accession number, as EDGAR writes it: 0000320193-20-000052. */
const ACCESSION = /^\d{10}-\d{2}-\d{6}$/;

/**
 * A decision's views as the drill-down shows them. `members` labels the XBRL facts'
 * groups, which are keyed by CIK, with the company's name and ticker at the decision.
 */
export function auditSections(
  views: readonly AuditView[],
  members: readonly BacktestMember[] | null,
): AuditSection[] {
  const companies = new Map(
    (members ?? []).flatMap((member) => (member.cik === null ? [] : [[member.cik, member]])),
  );
  return views.map((view) => {
    const tables = view.tables
      .map((table) => tableRow(table, view.knowledge_time, companies))
      .toSorted((a, b) => rank(a.table) - rank(b.table) || a.table.localeCompare(b.table));
    return {
      purpose: view.purpose,
      ...PURPOSES[view.purpose],
      knowledgeTime: shortTime(view.knowledge_time),
      moment: etDateTimeOf(view.knowledge_time),
      rows: view.rows,
      allKnown: tables.every((table) => table.known),
      tables,
    };
  });
}

/**
 * The groups of XBRL facts the decision's own view read, by CIK: for each company, the
 * newest filing a signal could use, and when it became public. "Newest filing read" is
 * all it says: a value can rest on older filings too, such as a 10-K behind a derived
 * fourth quarter.
 */
export function newestFilings(sections: readonly AuditSection[]): Map<string, AuditGroupRow> {
  const decision = sections.find((section) => section.purpose === "decision");
  const facts = decision?.tables.find((table) => table.table === "xbrl_facts");
  return new Map((facts?.groups ?? []).map((group) => [group.key, group]));
}

/**
 * Whether something that became public at `availableAt` was known at `knowledgeTime`,
 * to the microsecond the API writes. A time that can't be read isn't known.
 */
export function knownBy(availableAt: string, knowledgeTime: string): boolean {
  const at = instantOf(availableAt);
  const t = instantOf(knowledgeTime);
  return Number.isFinite(at) && Number.isFinite(t) && at <= t;
}

/** EDGAR's index page for a filing, from its company's CIK and its accession number. */
export function edgarIndexUrl(cik: number, accession: string): string | null {
  if (!Number.isInteger(cik) || !ACCESSION.test(accession)) return null;
  return `https://www.sec.gov/Archives/edgar/data/${cik}/${accession.replaceAll("-", "")}/${accession}-index.htm`;
}

function tableRow(
  table: AuditTable,
  knowledgeTime: string,
  companies: Map<number, BacktestMember>,
): AuditTableRow {
  const labels = TABLES[table.table] ?? { title: table.table, description: "" };
  return {
    table: table.table,
    ...labels,
    rows: table.rows,
    earliest: shortTime(table.earliest_available_at),
    newest: shortTime(table.latest_available_at),
    known: knownBy(table.latest_available_at, knowledgeTime),
    groups: table.groups
      .map((group) => groupRow(table.table, group, knowledgeTime, companies))
      .toSorted((a, b) => a.label.localeCompare(b.label)),
  };
}

function groupRow(
  table: string,
  group: AuditGroup,
  knowledgeTime: string,
  companies: Map<number, BacktestMember>,
): AuditGroupRow {
  const key = String(group.key);
  let label = key;
  let detail: string | null = null;
  let isKey = true;
  if (table === "xbrl_facts" && typeof group.key === "number") {
    const company = companies.get(group.key);
    label = company
      ? `${company.name}${company.ticker ? ` (${company.ticker})` : ""}`
      : `CIK ${key}`;
    detail = company ? `CIK ${key}` : null;
    isKey = false;
  } else if (table === "universe_members") {
    label = universeLabel(key);
    isKey = label === key;
  }
  return {
    key,
    label,
    detail,
    isKey,
    rows: group.rows,
    newest: shortTime(group.latest_available_at),
    known: knownBy(group.latest_available_at, knowledgeTime),
    source: source(table, group),
  };
}

function source(table: string, group: AuditGroup): AuditSource {
  const ref = group.latest_source_ref;
  if (table === "xbrl_facts" && typeof group.key === "number") {
    return { text: ref, href: edgarIndexUrl(group.key, ref) };
  }
  if (/^https:\/\//.test(ref)) {
    try {
      return { text: new URL(ref).hostname, href: ref };
    } catch {
      return { text: ref, href: null };
    }
  }
  return { text: ref, href: null };
}

/** A table's place in TABLE_ORDER; one it doesn't list comes last. */
function rank(table: string): number {
  const index = TABLE_ORDER.indexOf(table);
  return index < 0 ? TABLE_ORDER.length : index;
}

/** "Apr 30, 2020, 6:03 PM ET", or "—" for a time that can't be read. */
function shortTime(timestamp: string): string {
  const t = etDateTimeOf(timestamp);
  return t ? `${formatEtShortDate(t)}, ${formatEtTime(t)}` : "—";
}
