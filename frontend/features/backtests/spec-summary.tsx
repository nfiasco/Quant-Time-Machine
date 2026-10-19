import type { ExperimentSpec, SignalSpec } from "@/features/backtests/types";
import { cn } from "@/lib/utils";

const UNIVERSE_LABELS: Record<string, string> = {
  starter_large_caps: "Starter large caps",
};

const FILL_LABELS: Record<ExperimentSpec["schedule"]["fill"], string> = {
  same_day_close: "Same-day close",
  next_day_open: "Next-day open",
};

function describeDecision(decision: string): string {
  const match = /^first_trading_day (\d{2}:\d{2}) America\/New_York$/.exec(decision);
  return match ? `first trading day at ${match[1]} ET` : decision;
}

function describeSignal(signal: SignalSpec): string {
  switch (signal.type) {
    case "revenue_growth_acceleration":
      return "Revenue growth acceleration (year over year, quarterly)";
    case "momentum":
      return `Momentum, ${signal.lookback_months}-month lookback, skipping the last ${signal.skip_months}`;
  }
}

/**
 * An experiment spec in plain language, with the exact JSON one click away.
 * Assumptions (decision time, fill, costs) are always visible (NFR-3).
 */
export function SpecSummary({
  spec,
  showJson = true,
  className,
}: {
  spec: ExperimentSpec;
  showJson?: boolean;
  className?: string;
}) {
  const rows: { term: string; detail: React.ReactNode }[] = [
    {
      term: "Universe",
      detail: `${UNIVERSE_LABELS[spec.universe.id] ?? spec.universe.id} (point-in-time membership)`,
    },
    {
      term: "Period",
      detail: (
        <span className="font-mono tabular-nums">
          {spec.period.start} to {spec.period.end}
        </span>
      ),
    },
    {
      term: "Decision",
      detail: `Monthly, ${describeDecision(spec.schedule.decision)}`,
    },
    { term: "Fill", detail: FILL_LABELS[spec.schedule.fill] },
    {
      term: "Signals",
      detail: (
        <ul className="flex flex-col gap-1">
          {Object.entries(spec.signals).map(([id, signal]) => (
            <li key={id}>
              <code className="font-mono text-xs">{id}</code>: {describeSignal(signal)}
            </li>
          ))}
        </ul>
      ),
    },
    {
      term: "Filters",
      detail: (
        <span className="font-mono text-xs">
          {spec.filters.map((f) => `${f.signal} ${f.op} ${f.value}`).join(" and ")}
        </span>
      ),
    },
    {
      term: "Portfolio",
      detail: `${spec.portfolio.weighting === "equal" ? "Equal weight" : "Value weight"}${spec.portfolio.long_only ? ", long only" : ""}`,
    },
    { term: "Benchmark", detail: <span className="font-mono">{spec.benchmark}</span> },
    { term: "Costs", detail: `${spec.costs.bps_per_trade} bps per trade` },
  ];

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <dl className="grid grid-cols-1 gap-x-4 gap-y-2.5 sm:grid-cols-[7rem_1fr]">
        {rows.map((row) => (
          <div key={row.term} className="contents">
            <dt className="text-muted-foreground">{row.term}</dt>
            <dd className="min-w-0 text-pretty">{row.detail}</dd>
          </div>
        ))}
      </dl>
      {showJson ? (
        <details className="group rounded-lg border bg-muted/40">
          <summary className="cursor-pointer rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground select-none hover:text-foreground">
            View the spec JSON
          </summary>
          <pre className="max-h-80 overflow-auto border-t px-3 py-2 font-mono text-xs leading-relaxed">
            {JSON.stringify(spec, null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
