import Link from "next/link";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { decisionHref } from "@/features/backtests/decisions";
import {
  curveSummary,
  drawdownScale,
  ticksAreYears,
  timeTicks,
  type ChartPoint,
} from "@/features/backtests/equity";
import { ResultCharts } from "@/features/backtests/result-charts";
import type { BacktestPeriod } from "@/lib/api/types";
import { formatPercent, formatUsd } from "@/lib/format";
import { formatEtShortDate, parseIsoDate } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * The equity curve and the drawdown (S9.6), with what they show in words and every point
 * in a table, so the charts aren't the only place their numbers live (ACCESSIBILITY.md).
 */
export function ChartsCard({
  runId,
  points,
  periods,
  benchmark,
  selected,
}: {
  runId: string;
  points: ChartPoint[];
  periods: readonly BacktestPeriod[];
  benchmark: string;
  /** The decision the rebalance section shows, or null. */
  selected: string | null;
}) {
  // Each point but the last sits at a period's fill: link it to that period's decision.
  const decisionAt = new Map(periods.map((period) => [period.fill.session, period.decision]));
  const marker = periods.find((period) => period.decision === selected)?.fill.session ?? null;
  const ticks = timeTicks(points);

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Equity curve and drawdown</h2>
        </CardTitle>
        <CardDescription>
          $1 at the first fill, after costs, at each month&apos;s fill close in ET, beside{" "}
          {benchmark}&apos;s total return.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-pretty">{curveSummary(points, benchmark)}</p>
        <ResultCharts
          points={points}
          benchmark={benchmark}
          marker={marker}
          ticks={ticks}
          years={ticksAreYears(ticks)}
          drawdownTicks={drawdownScale(points).ticks}
        />
        <details className="group rounded-lg border">
          <summary className="cursor-pointer rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground select-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none">
            The numbers behind the charts ({points.length} closes)
          </summary>
          <div className="max-h-96 overflow-y-auto border-t">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Close (ET)</TableHead>
                  <TableHead scope="col" className="text-right">
                    Portfolio ($)
                  </TableHead>
                  <TableHead scope="col" className="text-right">
                    {benchmark} ($)
                  </TableHead>
                  <TableHead scope="col" className="text-right">
                    Portfolio drawdown (%)
                  </TableHead>
                  <TableHead scope="col" className="text-right">
                    {benchmark} drawdown (%)
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {points.map((point) => {
                  const decision = decisionAt.get(point.session);
                  const date = parseIsoDate(point.session);
                  const day = date ? formatEtShortDate(date) : point.session;
                  return (
                    <TableRow
                      key={point.session}
                      className={cn(point.session === marker && "bg-primary/10")}
                    >
                      <TableHead scope="row" className="font-mono text-xs font-normal tabular-nums">
                        {decision ? (
                          <Link
                            href={decisionHref(runId, decision, { anchor: true })}
                            className="underline underline-offset-4 hover:text-brand-ink"
                          >
                            {day}
                          </Link>
                        ) : (
                          day
                        )}
                      </TableHead>
                      <TableCell className="text-right font-mono tabular-nums">
                        {formatUsd(point.value)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {point.benchmark === null ? "—" : formatUsd(point.benchmark)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {formatPercent(point.drawdown)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {point.benchmarkDrawdown === null
                          ? "—"
                          : formatPercent(point.benchmarkDrawdown)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </details>
      </CardContent>
    </Card>
  );
}
