import { AssumptionsPanel } from "@/features/backtests/assumptions-panel";
import { ChartsCard } from "@/features/backtests/charts-card";
import { chartPoints, deepest } from "@/features/backtests/equity";
import { MetricsTable } from "@/features/backtests/metrics-table";
import { RebalanceSection } from "@/features/backtests/rebalance-section";
import type { RunResultsData } from "@/features/backtests/results-data";
import { WarningsPanel } from "@/features/backtests/warnings-panel";
import type { BacktestResult, BacktestRun } from "@/lib/api/types";

/**
 * A succeeded run's results (S9.6): the assumptions and warnings up front, then the
 * equity curve and drawdown, the metrics, and the drill-down into one rebalance.
 */
export function RunResults({
  run,
  result,
  data,
}: {
  run: BacktestRun;
  result: BacktestResult;
  data: RunResultsData;
}) {
  const points = chartPoints(result.equity_curve);
  // With one gap the benchmark has no metrics at all (metrics.md), drawdown included.
  const benchmarkFall = points.some((point) => point.benchmark === null)
    ? null
    : deepest(points, "benchmarkDrawdown");

  return (
    // The rebalance picker's data-pending dims what's about to change (GUIDELINES.md §6).
    <div className="group/results flex flex-col gap-6">
      <div className="grid gap-6 lg:grid-cols-2 lg:items-start">
        <AssumptionsPanel run={run} />
        <WarningsPanel runId={run.run_id} warnings={result.warnings} coverage={data.coverage} />
      </div>
      <ChartsCard
        runId={run.run_id}
        points={points}
        periods={result.periods}
        benchmark={run.spec.benchmark}
        selected={data.choice?.day ?? null}
      />
      <MetricsTable
        metrics={result.metrics}
        benchmark={run.spec.benchmark}
        benchmarkMaxDrawdown={benchmarkFall?.depth ?? null}
      />
      <RebalanceSection run={run} result={result} data={data} />
    </div>
  );
}
