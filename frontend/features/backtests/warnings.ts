import type { BacktestWarning, CoverageReport, CoverageRow } from "@/lib/api/types";
import { formatNumber, formatPercent } from "@/lib/format";

// What a run did without, and what it assumed instead, for the results page's warnings
// panel (S9.6): its warnings by kind (doc/reference/portfolio.md and metrics.md,
// "Warnings"), and its coverage report (doc/reference/runs.md, S6.7).

type WarningKind = BacktestWarning["kind"];

/** Each kind in plain words: a heading, and what the run did about it. */
export const WARNING_LABELS: Record<WarningKind, { title: string; explanation: string }> = {
  wiped_out: {
    title: "The run ended early",
    explanation: "The portfolio had nothing left, or couldn't pay for its trades.",
  },
  missing_benchmark: {
    title: "No benchmark price",
    explanation: "A period had no benchmark return, so the run isn't compared with it.",
  },
  delisted_exit: {
    title: "Holdings that stopped trading",
    explanation:
      "Each was valued at its last close, after the spec's assumed delisting return, and sold at the next fill.",
  },
  missing_price: {
    title: "Holdings without a closing bar",
    explanation: "Each was valued at its last close before its period ended.",
  },
  no_fill_price: {
    title: "Chosen without a price at the fill",
    explanation: "Each wasn't bought, or sold short, until the next fill.",
  },
  empty_portfolio: {
    title: "Decisions that held cash",
    explanation: "No member was chosen, so the portfolio held cash until the next fill.",
  },
  thin_ranking: {
    title: "Rankings shorter than their quantiles",
    explanation: "Too few members could be ranked, so one was held at each end.",
  },
  missing_signal: {
    title: "Members left out for a missing signal",
    explanation:
      "A signal a filter or the ranking needs had no value, so the decision left the member out.",
  },
  stopped_trading: {
    title: "Members that had stopped trading",
    explanation: "Each was still in the universe, but had no price, so it was left out.",
  },
  missing_risk_free: {
    title: "No risk-free rate known",
    explanation: "The period's rate was taken as 0 for the Sharpe ratio, beta, and alpha.",
  },
  fill_after_end: {
    title: "Decisions skipped",
    explanation: "Their trades would have filled after the period's last close.",
  },
};

/** The order the panel lists kinds in: what changes the result first. */
const ORDER = Object.keys(WARNING_LABELS) as WarningKind[];

export type WarningGroup = {
  kind: WarningKind;
  title: string;
  explanation: string;
  warnings: BacktestWarning[];
};

/** A run's warnings by kind, in the panel's order, each kind's in decision order. */
export function groupWarnings(warnings: readonly BacktestWarning[]): WarningGroup[] {
  return ORDER.flatMap((kind) => {
    const found = warnings.filter((warning) => warning.kind === kind);
    return found.length > 0 ? [{ kind, ...WARNING_LABELS[kind], warnings: found }] : [];
  });
}

/** One decision's warnings, in the panel's order. */
export function warningsAt(warnings: readonly BacktestWarning[], day: string): BacktestWarning[] {
  return groupWarnings(warnings.filter((warning) => warning.decision === day)).flatMap(
    (group) => group.warnings,
  );
}

const DATA_KINDS: Record<string, string> = {
  fundamentals: "fundamentals",
  prices: "prices",
  macro: "macro data",
};

/**
 * The coverage report in a sentence or two: "326 of 7,529 member-decisions (4.3%) were left
 * out for lack of data: 312 without fundamentals and 25 without prices."
 */
export function describeCoverage(report: CoverageReport): string {
  const { member_decisions: all, left_out: out, missing, exits } = report.totals;
  const decisions = `${formatNumber(report.decisions)} ${report.decisions === 1 ? "decision" : "decisions"}`;
  if (all === 0) return `The universe had no members at the run's ${decisions}.`;
  const lacked = Object.entries(missing)
    .filter(([, count]) => count > 0)
    .map(([kind, count]) => `${formatNumber(count)} without ${DATA_KINDS[kind] ?? kind}`);
  const share = formatPercent(out / all);
  const sentences = [
    out === 0
      ? `None of ${formatNumber(all)} member-decisions over ${decisions} was left out for lack of data.`
      : `${formatNumber(out)} of ${formatNumber(all)} member-decisions (${share}) over ${decisions} were left out for lack of data` +
        (lacked.length > 0 ? `: ${joinWords(lacked)}.` : "."),
  ];
  if (exits > 0) {
    sentences.push(
      exits === 1
        ? "1 holding was valued at its last close before its period ended."
        : `${formatNumber(exits)} holdings were valued at their last close before their periods ended.`,
    );
  }
  return sentences.join(" ");
}

/** The security-years with the most member-decisions left out, most first. */
export function worstCoverageRows(report: CoverageReport, most = 5): CoverageRow[] {
  return report.rows
    .filter((row) => row.left_out > 0)
    .toSorted(
      (a, b) =>
        b.left_out - a.left_out ||
        a.year - b.year ||
        (a.ticker ?? a.name).localeCompare(b.ticker ?? b.name),
    )
    .slice(0, most);
}

function joinWords(parts: readonly string[]): string {
  if (parts.length <= 1) return parts.join("");
  return `${parts.slice(0, -1).join(", ")} and ${parts.at(-1)}`;
}
