import type { ExperimentSpec, FilterSpec } from "@/features/backtests/types";

// How a spec's schedule and filters read in plain language, shared by the spec summary and
// the results page's assumptions (S9.5, S9.6).

/** What each fill rule means (doc/reference/time-model.md, rule 10 and D5). */
export const FILL_LABELS: Record<ExperimentSpec["schedule"]["fill"], string> = {
  same_day_close: "Same-day close",
  next_day_open: "Next-day open",
};

/** "first trading day at 09:30 ET", from the spec's `schedule.decision`. Another form is left as it is. */
export function describeDecision(decision: string): string {
  const match = /^first_trading_day (\d{2}:\d{2}) America\/New_York$/.exec(decision);
  return match ? `first trading day at ${match[1]} ET` : decision;
}

/** "rev_accel > 0". What the builder's form can't read yet, such as a blank value, is "?". */
export function describeFilter({ signal, op, value }: FilterSpec): string {
  return `${signal || "?"} ${op} ${Number.isFinite(value) ? value : "?"}`;
}
