import { describeFilter } from "@/features/backtests/describe-schedule";
import type { ExperimentSpec } from "@/features/backtests/types";
import type { BacktestHolding, BacktestMember, MemberOutcome, PricePoint } from "@/lib/api/types";
import { formatEtShortDate, parseIsoDate } from "@/lib/time";

// The members of the universe at one rebalance, for the results page's drill-down (S9.6):
// held or not, and why, from GET /v1/backtests/{run_id}/members, beside what each holding
// returned (`/holdings`). Eval task T5 asks exactly this: why June 1, 2020's decision
// didn't buy Apple.

export type MemberStatus = "held" | "chosen" | "out";

export type MemberRow = {
  key: string;
  ticker: string | null;
  name: string | null;
  /** The key of its XBRL facts in the audit, so the row can name the newest filing read. */
  cik: number | null;
  outcome: MemberOutcome;
  /** Held, chosen but not traded, or not chosen: how the row is marked. */
  status: MemberStatus;
  /** A word or two: "Held", "Not held", "Left out". */
  label: string;
  /** Why, in a sentence: "Failed rev_accel > 0". Empty for a holding: its weight says it. */
  detail: string;
  weight: number | null;
  signals: Record<string, number | null>;
  /** The holding's return from its fill to where it was valued; null if it wasn't held. */
  periodReturn: number | null;
  /** Where a holding whose bars ended early was valued, or null. */
  valuedEarly: string | null;
};

/** The order members are listed in: held first, then why the rest weren't. */
const ORDER: readonly MemberOutcome[] = [
  "held",
  "no_fill_price",
  "wiped_out",
  "outside_ranking",
  "failed_filter",
  "missing_signal",
  "stopped_trading",
];

/** What a decision made of a member, in words. */
export function describeOutcome(
  member: Pick<BacktestMember, "outcome" | "weight" | "missing" | "reasons" | "failed" | "rank">,
  spec: ExperimentSpec,
): Pick<MemberRow, "status" | "label" | "detail"> {
  const short = (member.weight ?? 0) < 0;
  switch (member.outcome) {
    case "held":
      return {
        status: "held",
        label: short ? "Held short" : "Held",
        detail: "",
      };
    case "no_fill_price":
      return {
        status: "chosen",
        label: short ? "Chosen, not shorted" : "Chosen, not bought",
        detail: short
          ? "No price at the fill, so the portfolio went without it"
          : "No price at the fill, so its share stayed in cash",
      };
    case "wiped_out":
      return {
        status: "chosen",
        label: "Chosen, not traded",
        detail: "The run ended at this decision, before its trades",
      };
    case "outside_ranking": {
      const rank = spec.portfolio.rank;
      return {
        status: "out",
        label: "Not held",
        detail:
          rank && member.rank !== null
            ? `Passed every filter, but ranked ${ordinal(member.rank)} by ${rank.signal}, outside the end the portfolio holds`
            : "Passed every filter, but too few members could be ranked",
      };
    }
    case "failed_filter":
      return {
        status: "out",
        label: "Not held",
        detail: `Failed ${member.failed
          .map((place) => {
            const condition = spec.filters[place];
            return condition ? describeFilter(condition) : `filter ${place + 1}`;
          })
          .join(" and ")}`,
      };
    case "missing_signal": {
      const reason = member.missing.map((id) => member.reasons[id]).find(Boolean);
      return {
        status: "out",
        label: "Left out",
        detail: `No ${member.missing.join(" or ")} value${reason ? `: ${reason}` : ""}`,
      };
    }
    case "stopped_trading":
      return {
        status: "out",
        label: "Left out",
        detail: "It had stopped trading by the decision",
      };
  }
}

/**
 * One rebalance's members, held first by weight, then the rest by why they weren't,
 * each with its holding's return when it was held. `periodEnd` is where the period ended,
 * so a holding valued before it can say so.
 */
export function memberRows(
  members: readonly BacktestMember[],
  holdings: readonly BacktestHolding[],
  spec: ExperimentSpec,
  periodEnd: PricePoint | null,
): MemberRow[] {
  const byTicker = new Map(holdings.map((holding) => [holding.ticker, holding]));
  return members
    .map((member, index): MemberRow => {
      const holding =
        member.outcome === "held" && member.ticker ? byTicker.get(member.ticker) : undefined;
      return {
        key: `${member.ticker ?? member.name}-${index}`,
        ticker: member.ticker,
        name: member.name,
        cik: member.cik,
        outcome: member.outcome,
        ...describeOutcome(member, spec),
        weight: member.weight,
        signals: member.signals,
        periodReturn: holding?.period_return ?? null,
        valuedEarly: holding ? valuedEarly(holding.exit, periodEnd) : null,
      };
    })
    .toSorted(compareRows);
}

/**
 * A rebalance's holdings alone, for a run saved before it kept every member (record
 * version 3): only what it held, with their signals.
 */
export function holdingRows(
  holdings: readonly BacktestHolding[],
  periodEnd: PricePoint | null,
): MemberRow[] {
  return holdings
    .map((holding): MemberRow => ({
      key: holding.ticker,
      ticker: holding.ticker,
      name: null,
      cik: null,
      outcome: "held",
      status: "held",
      label: holding.weight < 0 ? "Held short" : "Held",
      detail: "",
      weight: holding.weight,
      signals: holding.signals,
      periodReturn: holding.period_return,
      valuedEarly: valuedEarly(holding.exit, periodEnd),
    }))
    .toSorted(compareRows);
}

/** How many members the decision held, and how many it saw. */
export function heldCount(rows: readonly MemberRow[]): { held: number; total: number } {
  return { held: rows.filter((row) => row.outcome === "held").length, total: rows.length };
}

const COUNTED: Record<MemberOutcome, string> = {
  held: "held",
  no_fill_price: "chosen without a price at the fill",
  wiped_out: "chosen as the run ended",
  outside_ranking: "outside the ranking's ends",
  failed_filter: "failed a filter",
  missing_signal: "left out for a missing signal",
  stopped_trading: "had stopped trading",
};

/** "40 members: 10 held, 29 failed a filter, and 1 left out for a missing signal." */
export function describeCounts(rows: readonly MemberRow[]): string {
  if (rows.length === 0) return "The universe had no members at this decision.";
  const parts = ORDER.flatMap((outcome) => {
    const count = rows.filter((row) => row.outcome === outcome).length;
    return count > 0 ? [`${count} ${COUNTED[outcome]}`] : [];
  });
  const list =
    parts.length > 1 ? `${parts.slice(0, -1).join(", ")}, and ${parts.at(-1)}` : parts[0];
  return `${rows.length} ${rows.length === 1 ? "member" : "members"}: ${list}.`;
}

function compareRows(a: MemberRow, b: MemberRow): number {
  return (
    ORDER.indexOf(a.outcome) - ORDER.indexOf(b.outcome) ||
    Math.abs(b.weight ?? 0) - Math.abs(a.weight ?? 0) ||
    (a.ticker ?? a.name ?? "").localeCompare(b.ticker ?? b.name ?? "")
  );
}

function valuedEarly(exit: PricePoint, periodEnd: PricePoint | null): string | null {
  if (!periodEnd || exit.session === periodEnd.session) return null;
  const date = parseIsoDate(exit.session);
  return `Valued at its last close, on ${date ? formatEtShortDate(date) : exit.session}`;
}

function ordinal(n: number): string {
  const tens = n % 100;
  if (tens >= 11 && tens <= 13) return `${n}th`;
  return `${n}${["th", "st", "nd", "rd"][n % 10] ?? "th"}`;
}
