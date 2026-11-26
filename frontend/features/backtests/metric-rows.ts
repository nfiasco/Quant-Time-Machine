import type { BacktestMetrics } from "@/lib/api/types";
import { formatNumber, formatPercent, formatRatio, formatUsd } from "@/lib/format";

// The results page's metrics table (S9.6): every metric the run's metrics give, after
// costs, beside its benchmark's where there is one, with what each one means
// (doc/reference/metrics.md). A metric the run can't give is "—".

export type MetricValue = {
  text: string;
  /** Whether it's a gain or a loss, for a return; null otherwise. */
  tone: "positive" | "negative" | null;
  /** What the number counts, on a line of its own: "107 of 192 months". */
  detail?: string;
};

export type MetricRow = {
  label: string;
  /** What it measures, in a sentence. */
  definition: string;
  strategy: MetricValue;
  /** The benchmark's, or null for a row that's already about the benchmark. */
  benchmark: MetricValue | null;
  /**
   * Where the benchmark's value comes from when the run's metrics don't give it: drawn
   * from its curve, or not computed by the engine.
   */
  benchmarkNote?: "curve" | "not-computed";
};

export type MetricGroup = { title: string; rows: MetricRow[] };

const NONE: MetricValue = { text: "—", tone: null };

/**
 * The run's metrics in groups: growth, risk, against the benchmark, and trading.
 * `benchmarkMaxDrawdown` is drawn from the benchmark's curve (equity.ts), since the engine
 * gives only the portfolio's.
 */
export function metricGroups(
  metrics: BacktestMetrics,
  { benchmarkMaxDrawdown }: { benchmarkMaxDrawdown: number | null },
): MetricGroup[] {
  const hits = metrics.hit_rate === null ? null : Math.round(metrics.hit_rate * metrics.periods);
  return [
    {
      title: "Growth",
      rows: [
        {
          label: "Total return",
          definition: "What the portfolio gained from the first fill to the last close.",
          strategy: signed(metrics.total_return),
          benchmark: signed(metrics.benchmark_total_return),
        },
        {
          label: "Growth of $1",
          definition: "What $1 at the first fill was worth at the last close.",
          strategy: money(1 + metrics.total_return),
          benchmark:
            metrics.benchmark_total_return === null
              ? NONE
              : money(1 + metrics.benchmark_total_return),
        },
        {
          label: "Annual return (CAGR)",
          definition: "The yearly rate that compounds to the total return, over calendar days.",
          strategy: signed(metrics.cagr),
          benchmark: signed(metrics.benchmark_cagr),
        },
      ],
    },
    {
      title: "Risk",
      rows: [
        {
          label: "Volatility",
          definition: "How much the monthly returns vary, as a yearly figure (× √12).",
          strategy: plain(metrics.volatility, formatPercent),
          benchmark: NONE,
          benchmarkNote: "not-computed",
        },
        {
          label: "Sharpe ratio",
          definition: "The return over the risk-free rate for each unit of that variation, a year.",
          strategy: plain(metrics.sharpe, formatRatio),
          benchmark: NONE,
          benchmarkNote: "not-computed",
        },
        {
          label: "Max drawdown",
          definition: "The deepest fall from an earlier peak, seen at each month's fill.",
          strategy: plain(metrics.max_drawdown, formatPercent),
          benchmark: plain(benchmarkMaxDrawdown, formatPercent),
          benchmarkNote: "curve",
        },
      ],
    },
    {
      title: "Against the benchmark",
      rows: [
        {
          label: "Excess return",
          definition: "How much more the portfolio grew a year: its CAGR less the benchmark's.",
          strategy: signed(metrics.excess_return),
          benchmark: null,
        },
        {
          label: "Hit rate",
          definition: "The share of months the portfolio beat the benchmark; a tie isn't a hit.",
          strategy:
            metrics.hit_rate === null
              ? NONE
              : {
                  text: formatPercent(metrics.hit_rate),
                  tone: null,
                  detail: `${hits} of ${metrics.periods} months`,
                },
          benchmark: null,
        },
        {
          label: "Beta",
          definition: "How much the portfolio moved with the benchmark, over the risk-free rate.",
          strategy: plain(metrics.beta, formatRatio),
          benchmark: null,
        },
        {
          label: "Alpha",
          definition: "The return a year that the benchmark doesn't explain.",
          strategy: signed(metrics.alpha),
          benchmark: null,
        },
        {
          label: "Mean monthly excess return",
          definition: "The plain average of the monthly differences from the benchmark.",
          strategy: signed(metrics.mean_excess_return, 2),
          benchmark: null,
        },
        {
          label: "t-statistic",
          definition:
            "That average in standard errors from zero. Near 0 it could easily be chance; it takes more than about 2, and many months, to say otherwise.",
          strategy: plain(metrics.excess_t_stat, formatRatio),
          benchmark: null,
        },
      ],
    },
    {
      title: "Trading",
      rows: [
        {
          label: "Turnover",
          definition:
            "The share of the portfolio traded at a rebalance, both sides, after the first fill.",
          strategy: plain(metrics.turnover, formatPercent),
          benchmark: null,
        },
        {
          label: "Periods",
          definition: "Monthly holding periods, from the first fill to the last close.",
          strategy: {
            text: formatNumber(metrics.periods),
            tone: null,
            detail: `over ${formatRatio(metrics.years)} years`,
          },
          benchmark: null,
        },
      ],
    },
  ];
}

function signed(value: number | null, decimals: 1 | 2 = 1): MetricValue {
  if (value === null) return NONE;
  const text = formatPercent(value, { signed: true, decimals });
  return {
    text,
    tone: text.startsWith("+") ? "positive" : text.startsWith("−") ? "negative" : null,
  };
}

function plain(value: number | null, format: (value: number) => string): MetricValue {
  return value === null ? NONE : { text: format(value), tone: null };
}

function money(value: number): MetricValue {
  return { text: formatUsd(value), tone: null };
}
