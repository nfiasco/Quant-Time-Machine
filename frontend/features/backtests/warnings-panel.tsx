import Link from "next/link";
import { CircleAlertIcon, TriangleAlertIcon } from "lucide-react";

import { RetryButton } from "@/components/feedback/retry-button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { describeFailure } from "@/features/backtests/api-failure";
import { decisionHref } from "@/features/backtests/decisions";
import { describeCoverage, groupWarnings, worstCoverageRows } from "@/features/backtests/warnings";
import type { Settled } from "@/lib/api/errors";
import type { BacktestWarning, CoverageRow, GetResponse } from "@/lib/api/types";
import { formatNumber } from "@/lib/format";

/** A kind with this many warnings or fewer is open from the start. */
const OPEN_UP_TO = 5;

/**
 * What a run did without, and what it assumed instead (S9.6, NFR-3): its warnings by kind,
 * each linking to the rebalance it concerns, and its coverage report (S6.7).
 */
export function WarningsPanel({
  runId,
  warnings,
  coverage,
}: {
  runId: string;
  warnings: readonly BacktestWarning[];
  coverage: Settled<GetResponse<"/v1/backtests/{run_id}/coverage">>;
}) {
  const groups = groupWarnings(warnings);

  return (
    <Card id="warnings">
      <CardHeader>
        <CardTitle>
          <h2>Warnings and coverage</h2>
        </CardTitle>
        <CardDescription>
          {warnings.length === 0
            ? "The run noted no gap in its data."
            : `${formatNumber(warnings.length)} ${warnings.length === 1 ? "warning" : "warnings"}: what the run did without, and what it assumed instead.`}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {groups.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {groups.map((group) => (
              <li key={group.kind}>
                <details
                  open={group.warnings.length <= OPEN_UP_TO}
                  className="group/warning rounded-lg border"
                >
                  <summary className="flex cursor-pointer items-start gap-2 rounded-lg px-3 py-2 select-none hover:bg-muted/40 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none">
                    <Badge variant="outline" className="mt-0.5 font-mono tabular-nums">
                      {formatNumber(group.warnings.length)}
                    </Badge>
                    <span className="flex min-w-0 flex-col gap-0.5">
                      <span className="font-medium">{group.title}</span>
                      <span className="text-xs text-pretty text-muted-foreground">
                        {group.explanation}
                      </span>
                    </span>
                  </summary>
                  <ol className="flex max-h-72 flex-col gap-2 overflow-y-auto border-t px-3 py-2">
                    {group.warnings.map((warning, index) => (
                      <li key={index} className="flex flex-col gap-0.5 text-sm text-pretty">
                        <Link
                          href={decisionHref(runId, warning.decision, { anchor: true })}
                          className="w-fit font-mono text-xs text-muted-foreground tabular-nums underline underline-offset-4 hover:text-brand-ink"
                        >
                          {warning.decision}
                        </Link>
                        <span>{warning.message}</span>
                      </li>
                    ))}
                  </ol>
                </details>
              </li>
            ))}
          </ul>
        ) : null}

        <section aria-labelledby="coverage-heading" className="flex flex-col gap-2">
          <h3 id="coverage-heading" className="text-sm font-medium">
            Coverage
          </h3>
          <CoverageReport coverage={coverage} />
        </section>
      </CardContent>
    </Card>
  );
}

function CoverageReport({
  coverage,
}: {
  coverage: Settled<GetResponse<"/v1/backtests/{run_id}/coverage">>;
}) {
  if (!coverage.ok) {
    const { title, description } = describeFailure(coverage.failure);
    return (
      <Alert variant="destructive">
        <CircleAlertIcon />
        <AlertTitle>Couldn&apos;t load the coverage report: {title}</AlertTitle>
        <AlertDescription>
          <p>{description}</p>
          <div className="mt-2">
            <RetryButton />
          </div>
        </AlertDescription>
      </Alert>
    );
  }
  const report = coverage.value.coverage;
  if (!report) {
    return (
      <Alert variant="info">
        <TriangleAlertIcon />
        <AlertDescription>
          This run was saved before runs kept a coverage report (engine 1.1.0), so it has none.
        </AlertDescription>
      </Alert>
    );
  }
  const worst = worstCoverageRows(report);
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-pretty">{describeCoverage(report)}</p>
      {worst.length > 0 ? (
        <div className="flex flex-col gap-1">
          <p className="text-xs text-muted-foreground">Most left out, by company and year:</p>
          <ul className="flex flex-col divide-y rounded-lg border text-sm">
            {worst.map((row) => (
              <li
                key={`${row.ticker ?? row.name}-${row.year}`}
                className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 px-3 py-1.5"
              >
                <span className="min-w-0">
                  <span className="font-mono font-medium">{row.ticker ?? "—"}</span>{" "}
                  <span className="text-xs text-muted-foreground">
                    {row.name}, {row.year}
                  </span>
                </span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {formatNumber(row.left_out)} of {formatNumber(row.member_decisions)} left out
                  {lacked(row)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="text-xs text-pretty text-muted-foreground">
        The report counts only the universe&apos;s members: it can&apos;t see companies the universe
        never included because our prices don&apos;t cover them.
      </p>
    </div>
  );
}

function lacked(row: CoverageRow): string {
  const kinds = Object.entries(row.missing)
    .filter(([, count]) => count > 0)
    .map(([kind]) => kind);
  return kinds.length > 0 ? `, without ${kinds.join(" or ")}` : "";
}
