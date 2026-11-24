import { notFound } from "next/navigation";

import { routeMetadata, routes } from "@/config/navigation";
import { RunUnavailable, RunView } from "@/features/backtests/run-view";
import { getBacktestRun, isRunId } from "@/lib/api/backtests";
import { settle } from "@/lib/api/errors";

export const metadata = routeMetadata(routes.backtestRun);

/**
 * A run's page, by its ID (S9.5): the builder opens it when a run is submitted. It reads
 * the run on the server each time it renders, and `RunView` refreshes it until the run has
 * finished. The results page (S9.6) fills it out.
 */
export default async function BacktestRunPage(props: PageProps<"/backtests/[runId]">) {
  const { runId } = await props.params;
  if (!isRunId(runId)) notFound();

  const run = await settle(getBacktestRun(runId));
  return run.ok ? (
    <RunView run={run.value} />
  ) : (
    <RunUnavailable runId={runId} failure={run.failure} />
  );
}
