import { TriangleAlertIcon } from "lucide-react";

import { RetryButton } from "@/components/feedback/retry-button";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { routeMetadata, routes } from "@/config/navigation";
import { describeFailure } from "@/features/backtests/api-failure";
import { BacktestBuilder } from "@/features/backtests/backtest-builder";
import { canonicalPreset, findPreset } from "@/features/backtests/presets";
import { toSeriesChoices, toSignalKinds } from "@/features/backtests/signal-kinds";
import { getBacktestRun, isRunId } from "@/lib/api/backtests";
import { getCatalogSeries, getCatalogSignals } from "@/lib/api/catalog";
import { settle } from "@/lib/api/errors";

export const metadata = routeMetadata(routes.backtestBuilder);

/**
 * The backtest builder (S9.5). It starts from an earlier run's spec (`?from=<run_id>`, the
 * run page's "Edit and run again"), a preset (`?preset=canonical`), or the canonical
 * example. The signal and series catalogs load here, on the server; running a spec opens
 * its run's page.
 */
export default async function NewBacktestPage(props: PageProps<"/backtests/new">) {
  const { preset: presetId, from } = await props.searchParams;
  const preset = findPreset(presetId);
  const fromId = Array.isArray(from) ? from[0] : from;
  const runId = isRunId(fromId) ? fromId : null;

  const [signals, series, fromRun] = await Promise.all([
    settle(getCatalogSignals()),
    // Only the series' IDs and titles are used, which are the same at any moment.
    settle(getCatalogSeries(canonicalPreset.spec.period.end)),
    runId ? settle(getBacktestRun(runId)) : null,
  ]);
  const kinds = toSignalKinds(signals);
  const initialSpec = fromRun?.ok ? fromRun.value.spec : (preset?.spec ?? canonicalPreset.spec);

  let intro: React.ReactNode = null;
  if (fromRun?.ok) {
    intro = (
      <p className="text-sm text-pretty text-muted-foreground">
        Starting from run{" "}
        <code className="font-mono text-xs">{fromRun.value.run_id.slice(0, 12)}</code>,{" "}
        <span className="text-foreground">{fromRun.value.spec.name}</span>. Change what you like,
        then run it.
      </p>
    );
  } else if (fromId) {
    intro = (
      <Alert variant="warning">
        <TriangleAlertIcon />
        <AlertTitle>Couldn&apos;t open that run, so this starts from the example</AlertTitle>
        <AlertDescription>
          {fromRun
            ? describeFailure(fromRun.failure).description
            : "The link's run ID isn't 64 hex digits."}
        </AlertDescription>
      </Alert>
    );
  } else if (preset) {
    intro = (
      <blockquote className="border-l-2 border-primary/40 pl-3 text-sm text-pretty text-muted-foreground italic">
        {preset.question}
      </blockquote>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={routes.backtestBuilder.title}
        description={routes.backtestBuilder.description}
      />

      {intro}

      {kinds.loaded ? null : (
        <Alert variant="warning">
          <TriangleAlertIcon />
          <AlertTitle>Couldn&apos;t load the signal catalog</AlertTitle>
          <AlertDescription>
            <p>
              {signals.ok ? null : describeFailure(signals.failure).description} Until it loads, the
              signals below can&apos;t be added or changed.
            </p>
            <RetryButton />
          </AlertDescription>
        </Alert>
      )}

      <BacktestBuilder
        key={runId ?? preset?.id ?? "default"}
        initialSpec={initialSpec}
        kinds={kinds}
        series={toSeriesChoices(series)}
      />
    </div>
  );
}
