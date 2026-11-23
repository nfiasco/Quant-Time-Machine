// What a run's page says about the run (S9.5), from GET /v1/backtests/{run_id}: where it
// has got to (queued, running with its progress, succeeded, or failed), and once it has
// succeeded, its headline numbers. Plain functions, so the page and its tests agree.

import type { BacktestMetrics, BacktestRun } from "@/lib/api/types";
import { formatPercent, formatRatio } from "@/lib/format";

export type RunState = {
  /** The status in a word, for its badge. */
  label: string;
  badge: "secondary" | "outline" | "positive" | "destructive";
  /**
   * One sentence for the page's live region. It changes only with the status, so a screen
   * reader isn't read the count every time the page refreshes.
   */
  sentence: string;
  /** How far a running run has come, or null (also for a moment after it starts). */
  progress: { done: number; total: number; percent: number } | null;
  /** True while the run can still change, so the page keeps refreshing. */
  pending: boolean;
};

export function describeRun(run: Pick<BacktestRun, "status" | "progress" | "error">): RunState {
  switch (run.status) {
    case "queued":
      return {
        label: "Queued",
        badge: "secondary",
        sentence: "The run is waiting for the one ahead of it.",
        progress: null,
        pending: true,
      };
    case "running": {
      const total = run.progress?.decisions_total ?? 0;
      const done = Math.min(run.progress?.decisions_done ?? 0, total);
      return {
        label: "Running",
        badge: "outline",
        sentence: "The run is in progress.",
        progress: total > 0 ? { done, total, percent: Math.floor((done / total) * 100) } : null,
        pending: true,
      };
    }
    case "succeeded":
      return {
        label: "Succeeded",
        badge: "positive",
        sentence: "The run has finished.",
        progress: null,
        pending: false,
      };
    case "failed":
      return {
        label: "Failed",
        badge: "destructive",
        // The page shows why in an alert, which a screen reader announces as it appears.
        sentence: "The run failed, so it has no result.",
        progress: null,
        pending: false,
      };
  }
}

/** "13 of 36 decisions". */
export function describeProgress({ done, total }: { done: number; total: number }): string {
  return `${done} of ${total} ${total === 1 ? "decision" : "decisions"}`;
}

export type Headline = {
  label: string;
  /** "—" for a metric the run can't give, such as a Sharpe ratio from one period. */
  value: string;
  /** What to compare it with, or how it was measured. */
  detail: string;
  /** Whether it's a gain or a loss, for a return; null otherwise. */
  tone: "positive" | "negative" | null;
};

/**
 * A run's headline numbers, after costs, beside its benchmark's where it has one: the annual
 * return, the total return, the Sharpe ratio, and the deepest drawdown
 * (doc/reference/metrics.md). Returns keep their sign, so they don't rest on color.
 */
export function headlineMetrics(metrics: BacktestMetrics, benchmark: string): Headline[] {
  const versus = (value: number | null) =>
    value === null
      ? `${benchmark}: not available`
      : `${benchmark}: ${formatPercent(value, { signed: true })}`;
  return [
    {
      label: "Annual return (CAGR)",
      ...signedReturn(metrics.cagr),
      detail: versus(metrics.benchmark_cagr),
    },
    {
      label: "Total return",
      ...signedReturn(metrics.total_return),
      detail: versus(metrics.benchmark_total_return),
    },
    {
      label: "Sharpe ratio",
      value: metrics.sharpe === null ? "—" : formatRatio(metrics.sharpe),
      detail:
        metrics.volatility === null
          ? "Volatility not available"
          : `Volatility ${formatPercent(metrics.volatility)} a year`,
      tone: null,
    },
    {
      label: "Max drawdown",
      value: formatPercent(metrics.max_drawdown),
      detail: "The deepest fall from an earlier peak",
      tone: null,
    },
  ];
}

function signedReturn(value: number | null): Pick<Headline, "value" | "tone"> {
  if (value === null) return { value: "—", tone: null };
  const text = formatPercent(value, { signed: true });
  return {
    value: text,
    tone: text.startsWith("+") ? "positive" : text.startsWith("−") ? "negative" : null,
  };
}
