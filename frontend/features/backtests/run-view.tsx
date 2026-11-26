import Link from "next/link";
import {
  CircleAlertIcon,
  CircleCheckIcon,
  CircleXIcon,
  ClockIcon,
  LoaderCircleIcon,
  PencilIcon,
  PlusIcon,
  SearchXIcon,
  type LucideIcon,
} from "lucide-react";

import { ErrorState } from "@/components/feedback/error-state";
import { RetryButton } from "@/components/feedback/retry-button";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Progress } from "@/components/ui/progress";
import { routes } from "@/config/navigation";
import { describeFailure } from "@/features/backtests/api-failure";
import { RerunButton } from "@/features/backtests/rerun-button";
import { RunRefresher } from "@/features/backtests/run-refresher";
import { RunResults } from "@/features/backtests/run-results";
import type { RunResultsData } from "@/features/backtests/results-data";
import {
  describeProgress,
  describeRun,
  headlineMetrics,
  type RunState,
} from "@/features/backtests/run-status";
import { SpecSummary } from "@/features/backtests/spec-summary";
import { backtestPath } from "@/lib/api/backtests";
import { apiUrl } from "@/lib/api/client";
import type { ApiFailure } from "@/lib/api/errors";
import type { BacktestRun } from "@/lib/api/types";
import { etDateTimeOf, formatEtDate, formatEtDateTime, parseIsoDate } from "@/lib/time";
import { cn } from "@/lib/utils";

const STATUS_ICONS: Record<BacktestRun["status"], LucideIcon> = {
  queued: ClockIcon,
  running: LoaderCircleIcon,
  succeeded: CircleCheckIcon,
  failed: CircleXIcon,
};

/**
 * A run's page (S9.5): its status while it's queued or running, or why it failed, with
 * the spec it ran and what it ran on. It refreshes itself until the run has finished.
 * Once the run has succeeded it's the results page (S9.6): the headline numbers, then
 * `RunResults` with `results`, what the page read beyond the run.
 */
export function RunView({
  run,
  results = null,
}: {
  run: BacktestRun;
  results?: RunResultsData | null;
}) {
  const state = describeRun(run);
  const StatusIcon = STATUS_ICONS[run.status];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={run.spec.name}
        description={
          <>
            Backtest run <code className="font-mono text-xs">{run.run_id.slice(0, 12)}</code>, on
            data version <code className="font-mono text-xs">{run.data_version}</code>.
          </>
        }
        badge={
          <Badge variant={state.badge}>
            <StatusIcon
              data-icon="inline-start"
              className={cn(run.status === "running" && "motion-safe:animate-spin")}
            />
            {state.label}
          </Badge>
        }
        actions={
          <Button asChild variant="outline">
            <Link href={`/backtests/new?from=${run.run_id}`}>
              <PencilIcon data-icon="inline-start" />
              Edit and run again
            </Link>
          </Button>
        }
      />
      <RunRefresher active={state.pending} />

      <RunStatusCard run={run} state={state} />

      {run.status === "succeeded" && run.result && results ? (
        <RunResults run={run} result={run.result} data={results} />
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>The spec</h2>
            </CardTitle>
            <CardDescription>What the run tested, with every default written out.</CardDescription>
          </CardHeader>
          <CardContent>
            <SpecSummary spec={run.spec} />
          </CardContent>
        </Card>
        <RunDetails run={run} />
      </div>
    </div>
  );
}

function RunStatusCard({ run, state }: { run: BacktestRun; state: RunState }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Status</h2>
        </CardTitle>
        {/* The same element in every status, so a screen reader hears when it changes. */}
        <CardDescription role="status">{state.sentence}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {run.status === "queued" ? (
          <p className="text-sm text-pretty text-muted-foreground">
            The server runs one backtest at a time and keeps up to five waiting. This page updates
            by itself.
          </p>
        ) : null}

        {run.status === "running" ? <RunningProgress run={run} state={state} /> : null}

        {run.status === "failed" ? (
          <Alert variant="destructive">
            <CircleAlertIcon />
            <AlertTitle>No result</AlertTitle>
            <AlertDescription>
              <p>{run.error ?? "The run stopped without saying why."}</p>
              <div className="mt-3 flex flex-wrap items-start gap-2">
                <RerunButton spec={run.spec} />
              </div>
            </AlertDescription>
          </Alert>
        ) : null}

        {run.status === "succeeded" && run.result ? <RunHeadline run={run} /> : null}
      </CardContent>
    </Card>
  );
}

function RunningProgress({ run, state }: { run: BacktestRun; state: RunState }) {
  const started = run.started_at ? etDateTimeOf(run.started_at) : null;
  const progress = state.progress;
  return (
    <div className="flex flex-col gap-2">
      <Progress
        value={progress?.percent ?? 0}
        aria-label="Decisions done"
        aria-valuetext={progress ? describeProgress(progress) : "Starting"}
      />
      <p className="text-sm text-muted-foreground tabular-nums">
        {progress ? `${describeProgress(progress)} done` : "Starting…"}
        {started ? ` · started ${formatEtDateTime(started)}` : null}
      </p>
    </div>
  );
}

function RunHeadline({ run }: { run: BacktestRun }) {
  if (!run.result) return null;
  const { metrics, warnings } = run.result;
  const start = parseIsoDate(metrics.start.session);
  const end = parseIsoDate(metrics.end.session);

  return (
    <div className="flex flex-col gap-4">
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {headlineMetrics(metrics, run.spec.benchmark).map((headline) => (
          <div key={headline.label} className="flex flex-col gap-1 rounded-lg border p-3">
            <dt className="text-xs text-muted-foreground">{headline.label}</dt>
            <dd
              className={cn(
                "font-mono text-xl font-semibold tabular-nums",
                headline.tone === "positive" && "text-positive",
                headline.tone === "negative" && "text-negative",
              )}
            >
              {headline.value}
            </dd>
            <dd className="text-xs text-muted-foreground tabular-nums">{headline.detail}</dd>
          </div>
        ))}
      </dl>
      <p className="text-sm text-pretty text-muted-foreground">
        After costs, over {metrics.periods} monthly {metrics.periods === 1 ? "period" : "periods"}
        {start && end
          ? ` from the close on ${formatEtDate(start)} to the close on ${formatEtDate(end)}`
          : ""}
        .{" "}
        {warnings.length === 0 ? (
          "The run noted no gap in its data."
        ) : (
          <>
            The run noted{" "}
            <a href="#warnings" className="underline underline-offset-4 hover:text-brand-ink">
              {warnings.length} {warnings.length === 1 ? "warning" : "warnings"}
            </a>{" "}
            about missing data, and what it assumed instead.
          </>
        )}
      </p>
    </div>
  );
}

function RunDetails({ run }: { run: BacktestRun }) {
  const times = [
    ["Submitted", run.submitted_at],
    ["Started", run.started_at],
    ["Finished", run.finished_at],
  ] as const;
  const rows: { term: string; detail: React.ReactNode }[] = [
    {
      term: "Run ID",
      detail: <code className="font-mono text-xs break-all">{run.run_id}</code>,
    },
    { term: "Data version", detail: <code className="font-mono text-xs">{run.data_version}</code> },
    { term: "Engine", detail: <code className="font-mono text-xs">{run.engine_version}</code> },
    {
      term: "Code",
      detail: run.git_sha ? (
        <code className="font-mono text-xs">{run.git_sha.slice(0, 12)}</code>
      ) : (
        "Not recorded yet"
      ),
    },
    ...times.flatMap(([term, timestamp]) => {
      const moment = timestamp ? etDateTimeOf(timestamp) : null;
      return moment ? [{ term, detail: formatEtDateTime(moment) }] : [];
    }),
  ];

  return (
    <Card size="sm" className="self-start">
      <CardHeader>
        <CardTitle>
          <h2>What it ran on</h2>
        </CardTitle>
        <CardDescription>The same spec on the same data version is the same run.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <dl className="grid grid-cols-[6.5rem_1fr] gap-x-3 gap-y-2">
          {rows.map((row) => (
            <div key={row.term} className="contents">
              <dt className="text-muted-foreground">{row.term}</dt>
              <dd className="min-w-0">{row.detail}</dd>
            </div>
          ))}
        </dl>
        <a
          href={apiUrl(backtestPath(run.run_id))}
          className="text-xs text-muted-foreground underline underline-offset-4 hover:text-brand-ink"
        >
          The run as the API serves it (JSON)
        </a>
      </CardContent>
    </Card>
  );
}

/** Why a run's page has no run to show: no such run, or the API didn't answer. */
export function RunUnavailable({ runId, failure }: { runId: string; failure: ApiFailure }) {
  const header = (
    <PageHeader
      title={routes.backtestRun.title}
      description={
        <>
          Run <code className="font-mono text-xs">{runId.slice(0, 12)}</code>
        </>
      }
    />
  );

  if (failure.kind === "response" && failure.status === 404) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <Empty className="border border-dashed">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <SearchXIcon />
            </EmptyMedia>
            <EmptyTitle>No run with this ID</EmptyTitle>
            {/* The API's sentence holds the 64-digit ID, which must wrap on a phone. */}
            <EmptyDescription className="wrap-anywhere">
              {failure.message} A run is reached by its ID, and runs aren&apos;t listed yet.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button asChild size="sm">
              <Link href={routes.backtestBuilder.href}>
                <PlusIcon data-icon="inline-start" />
                Build a backtest
              </Link>
            </Button>
          </EmptyContent>
        </Empty>
      </div>
    );
  }

  const { title, description } = describeFailure(failure);
  return (
    <div className="flex flex-col gap-6">
      {header}
      {/* The API may be restarting: keep trying, more slowly. */}
      <RunRefresher active intervalMs={5_000} />
      <ErrorState
        title={title}
        description={`${description} This page tries again by itself.`}
        actions={<RetryButton />}
      />
    </div>
  );
}
