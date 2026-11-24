import { describeDelisting } from "@/features/backtests/describe-delisting";
import { describePortfolio } from "@/features/backtests/describe-portfolio";
import { describeSignal } from "@/features/backtests/describe-signal";
import type { ExperimentSpec } from "@/features/backtests/types";
import { universeLabel } from "@/features/backtests/universes";
import { cn } from "@/lib/utils";

const FILL_LABELS: Record<ExperimentSpec["schedule"]["fill"], string> = {
  same_day_close: "Same-day close",
  next_day_open: "Next-day open",
};

function describeDecision(decision: string): string {
  const match = /^first_trading_day (\d{2}:\d{2}) America\/New_York$/.exec(decision);
  return match ? `first trading day at ${match[1]} ET` : decision;
}

/** "rev_accel > 0". What the builder's form can't read yet, such as a blank value, is "?". */
function describeFilter({ signal, op, value }: ExperimentSpec["filters"][number]): string {
  return `${signal || "?"} ${op} ${Number.isFinite(value) ? value : "?"}`;
}

/**
 * An experiment spec in plain language, with the exact JSON one click away.
 * Assumptions (decision time, fill, costs, delistings) are always visible (NFR-3).
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
      detail: `${universeLabel(spec.universe.id)} (point-in-time membership)`,
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
      detail:
        Object.keys(spec.signals).length > 0 ? (
          <ul className="flex flex-col gap-1">
            {Object.entries(spec.signals).map(([id, signal]) => (
              <li key={id}>
                <code className="font-mono text-xs">{id}</code>: {describeSignal(signal)}
              </li>
            ))}
          </ul>
        ) : (
          "None"
        ),
    },
    {
      term: "Filters",
      detail:
        spec.filters.length > 0 ? (
          <span className="font-mono text-xs">
            {spec.filters.map(describeFilter).join(" and ")}
          </span>
        ) : (
          "None: every member passes"
        ),
    },
    { term: "Portfolio", detail: describePortfolio(spec.portfolio) },
    { term: "Benchmark", detail: <span className="font-mono">{spec.benchmark}</span> },
    {
      term: "Costs",
      detail: Number.isFinite(spec.costs.bps_per_trade)
        ? `${spec.costs.bps_per_trade} bps per trade`
        : "—",
    },
    { term: "Delistings", detail: describeDelisting(spec.delisting) },
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
