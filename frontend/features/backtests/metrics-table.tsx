import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { metricGroups, type MetricRow, type MetricValue } from "@/features/backtests/metric-rows";
import type { BacktestMetrics } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const NOTES: Record<NonNullable<MetricRow["benchmarkNote"]>, { mark: string; text: string }> = {
  "not-computed": { mark: "*", text: "The engine doesn't compute this for the benchmark." },
  curve: { mark: "†", text: "Drawn from the benchmark's monthly curve, as the portfolio's is." },
};

/**
 * Every metric a run gives, after costs, beside its benchmark's, with what each one
 * measures (S9.6; doc/reference/metrics.md).
 */
export function MetricsTable({
  metrics,
  benchmark,
  benchmarkMaxDrawdown,
}: {
  metrics: BacktestMetrics;
  benchmark: string;
  benchmarkMaxDrawdown: number | null;
}) {
  const groups = metricGroups(metrics, { benchmarkMaxDrawdown });
  const notes = new Set(groups.flatMap((group) => group.rows.map((row) => row.benchmarkNote)));

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Metrics</h2>
        </CardTitle>
        <CardDescription>
          After costs. A metric the run can&apos;t give, such as a Sharpe ratio from one period, is
          &ldquo;—&rdquo;.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Metric</TableHead>
              <TableHead scope="col" className="text-right">
                Portfolio
              </TableHead>
              <TableHead scope="col" className="text-right">
                {benchmark}
              </TableHead>
            </TableRow>
          </TableHeader>
          {groups.map((group) => (
            <TableBody key={group.title}>
              <TableRow className="hover:bg-transparent">
                <TableHead
                  scope="colgroup"
                  colSpan={3}
                  className="h-8 bg-muted/40 text-xs text-muted-foreground"
                >
                  {group.title}
                </TableHead>
              </TableRow>
              {group.rows.map((row) => (
                <TableRow key={row.label}>
                  <TableHead scope="row" className="h-auto py-2 font-normal whitespace-normal">
                    <span className="font-medium">{row.label}</span>
                    <span className="block max-w-prose text-xs text-pretty text-muted-foreground">
                      {row.definition}
                    </span>
                  </TableHead>
                  <Value value={row.strategy} />
                  {row.benchmark ? (
                    <Value
                      value={row.benchmark}
                      mark={row.benchmarkNote ? NOTES[row.benchmarkNote].mark : undefined}
                    />
                  ) : (
                    <TableCell aria-label="Not applicable" />
                  )}
                </TableRow>
              ))}
            </TableBody>
          ))}
        </Table>
        <ul className="flex flex-col gap-0.5 text-xs text-muted-foreground">
          {(Object.keys(NOTES) as (keyof typeof NOTES)[])
            .filter((note) => notes.has(note))
            .map((note) => (
              <li key={note}>
                {NOTES[note].mark} {NOTES[note].text}
              </li>
            ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function Value({ value, mark }: { value: MetricValue; mark?: string }) {
  return (
    <TableCell
      className={cn(
        "text-right align-top font-mono tabular-nums",
        value.tone === "positive" && "text-positive",
        value.tone === "negative" && "text-negative",
      )}
    >
      {value.text}
      {mark ? <span className="ml-0.5 text-muted-foreground">{mark}</span> : null}
      {value.detail ? (
        <span className="block font-sans text-xs text-muted-foreground">{value.detail}</span>
      ) : null}
    </TableCell>
  );
}
