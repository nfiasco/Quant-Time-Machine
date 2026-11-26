import type { BacktestResult } from "@/lib/api/types";
import { formatEtDate, parseIsoDate } from "@/lib/time";

// Which of a run's decisions the results page drills into (S9.6). The choice lives in the
// URL as `?decision=2020-06-01`, the API's own name for it (GUIDELINES.md, "Data and URL
// state"), so a link to one rebalance can be shared.

/**
 * A run's decision days, in order: each that traded, and one the run ended on. A decision
 * the run made without a holding period has a warning dated to it, such as `wiped_out` or
 * the `stopped_trading` of its members; `fill_after_end` dates a decision that was skipped,
 * so it doesn't count.
 */
export function decisionDays(result: Pick<BacktestResult, "periods" | "warnings">): string[] {
  const days = new Set(result.periods.map((period) => period.decision));
  const last = result.periods.at(-1)?.decision;
  for (const warning of result.warnings) {
    if (warning.kind === "fill_after_end") continue;
    // Only a decision after the last period can be one without its own: every other
    // warning is dated to a decision that traded.
    if (last === undefined || warning.decision > last) days.add(warning.decision);
  }
  return [...days].sort();
}

export type DecisionChoice = {
  /** The decision shown. */
  day: string;
  previous: string | null;
  next: string | null;
  /** Why the address's day isn't the one shown, as a sentence; null when it is. */
  notice: string | null;
};

/**
 * The decision to show for the address's `decision`: that day if the run made a decision on
 * it; otherwise the latest decision before it, or the first, with a notice; and the last
 * decision when there's none. Null for a run without decisions.
 */
export function chooseDecision(
  days: readonly string[],
  raw: string | string[] | undefined,
): DecisionChoice | null {
  if (days.length === 0) return null;
  const wanted = Array.isArray(raw) ? raw[0] : raw;
  const pick = (index: number, notice: string | null): DecisionChoice => ({
    day: days[index],
    previous: index > 0 ? days[index - 1] : null,
    next: index < days.length - 1 ? days[index + 1] : null,
    notice,
  });

  if (wanted === undefined || wanted === "") return pick(days.length - 1, null);
  const exact = days.indexOf(wanted);
  if (exact >= 0) return pick(exact, null);

  const date = parseIsoDate(wanted);
  if (!date) {
    return pick(
      days.length - 1,
      `“${wanted}” isn't a date such as 2020-06-01, so this shows the last decision.`,
    );
  }
  const before = days.findLastIndex((day) => day < wanted);
  const index = before >= 0 ? before : 0;
  const shown = formatDay(days[index]);
  return pick(
    index,
    before >= 0
      ? `The run made no decision on ${formatEtDate(date)}, so this shows the one before it, on ${shown}.`
      : `The run's first decision was on ${shown}, after ${formatEtDate(date)}, so this shows that one.`,
  );
}

/** The run's page at one decision, such as `/backtests/9dfe…?decision=2020-06-01#rebalance`. */
export function decisionHref(
  runId: string,
  day: string,
  { anchor = false } = {},
): `/backtests/${string}` {
  return `/backtests/${runId}?decision=${day}${anchor ? "#rebalance" : ""}`;
}

/** "June 1, 2020" for a decision's day. */
export function formatDay(day: string): string {
  const date = parseIsoDate(day);
  return date ? formatEtDate(date) : day;
}
