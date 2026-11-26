import { notFound } from "next/navigation";

import { routeMetadata, routes } from "@/config/navigation";
import { loadRunResults } from "@/features/backtests/results-data";
import { RunUnavailable, RunView } from "@/features/backtests/run-view";
import { getBacktestRun, isRunId } from "@/lib/api/backtests";
import { settle } from "@/lib/api/errors";

export const metadata = routeMetadata(routes.backtestRun);

/**
 * A run's page, by its ID (S9.5), which the builder opens when a run is submitted, and
 * its results page once it has succeeded (S9.6). It reads the run on the server each time
 * it renders, and `RunView` refreshes it until the run has finished. A finished run's
 * page also reads its coverage and one rebalance's parts: `?decision=2020-06-01`, or the
 * last rebalance.
 */
export default async function BacktestRunPage(props: PageProps<"/backtests/[runId]">) {
  const [{ runId }, { decision }] = await Promise.all([props.params, props.searchParams]);
  if (!isRunId(runId)) notFound();

  const run = await settle(getBacktestRun(runId));
  if (!run.ok) return <RunUnavailable runId={runId} failure={run.failure} />;

  const { result } = run.value;
  const results =
    run.value.status === "succeeded" && result
      ? await loadRunResults(runId, result, decision)
      : null;
  return <RunView run={run.value} results={results} />;
}
