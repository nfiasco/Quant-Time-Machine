import { CheckIcon, CircleDashedIcon, HistoryIcon, TriangleAlertIcon } from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { routeMetadata, routes } from "@/config/navigation";
import { RevisionChart, type ChartPoint } from "@/features/revisions/revision-chart";
import { settle, type ApiFailure } from "@/lib/api/errors";
import { ALL_VINTAGES_AS_OF, getRevisions } from "@/lib/api/revisions";
import type { MacroObservation } from "@/lib/api/types";
import { formatMacroValue } from "@/lib/format";
import { revisionsHref } from "@/lib/revisions-link";
import {
  etDateTimeOf,
  formatEtDateTime,
  formatEtShortDate,
  formatPeriod,
  instantOf,
  parseAsOf,
  toAsOfParam,
} from "@/lib/time";
import { cn } from "@/lib/utils";

export const metadata = routeMetadata(routes.revisions);

type Status = "visible" | "replaced" | "later" | "published";

const SERIES_PATTERN = /^[A-Z0-9_]{1,32}$/;

function first(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

/** A month from the form (`1990-01`) or a full date (`1990-01-01`), as the API writes it. */
function normalizePeriod(value: string): string | null {
  if (/^\d{4}-\d{2}$/.test(value)) return `${value}-01`;
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
}

const rowKey = (v: MacroObservation) => `${v.vintage_date}|${v.available_at}`;

function dateText(timestamp: string): string {
  const t = etDateTimeOf(timestamp);
  return t ? formatEtShortDate(t) : timestamp;
}

function failureText(failure: ApiFailure): string {
  if (failure.kind === "timeout") return "The API took too long to answer.";
  if (failure.kind === "unreachable") return "The API could not be reached. Is the backend running?";
  const details = failure.details.map((d) => `${d.field}: ${d.message}`).join(" ");
  return details ? `${failure.message} ${details}` : failure.message;
}

/**
 * The macro revision viewer (S9.3). The URL holds the view: `series`, `period`, and an
 * optional `as_of` (the Time Machine's moment). The page asks the API twice for the same
 * observation: every version, then the versions public at `as_of`. A version is "known"
 * when the second answer includes it, and the newest of those is the value visible then.
 */
export default async function RevisionsPage(props: PageProps<"/revisions">) {
  const params = await props.searchParams;
  const series = first(params.series).toUpperCase();
  const periodInput = first(params.period);
  const period = normalizePeriod(periodInput);
  const moment = parseAsOf(first(params.as_of) || undefined);
  const asked = series !== "" || periodInput !== "";
  const valid = SERIES_PATTERN.test(series) && period !== null;

  const [all, atMoment] =
    valid && period
      ? await Promise.all([
          settle(getRevisions({ series, period, asOf: ALL_VINTAGES_AS_OF })),
          moment ? settle(getRevisions({ series, period, asOf: toAsOfParam(moment) })) : null,
        ])
      : [null, null];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={routes.revisions.title} description={routes.revisions.description} />

      <Card>
        <CardContent>
          <form action="/revisions" method="get" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_auto] lg:items-end">
            <div className="flex flex-col gap-2">
              <Label htmlFor="series">Series</Label>
              <Input id="series" name="series" defaultValue={series} placeholder="UNRATE" autoComplete="off" required />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="period">Observation period</Label>
              <Input id="period" name="period" type="month" defaultValue={period ? period.slice(0, 7) : ""} required />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="as_of">Time Machine moment (optional)</Label>
              <Input id="as_of" name="as_of" type="datetime-local" defaultValue={moment ? toAsOfParam(moment) : ""} />
            </div>
            <Button type="submit">Show revisions</Button>
          </form>
        </CardContent>
      </Card>

      {!asked ? (
        <Card>
          <CardHeader>
            <CardTitle>Pick a series and a month</CardTitle>
            <CardDescription>
              See every value published for one observation, from its first release to its latest
              revision. Try{" "}
              <Link
                className="underline underline-offset-4"
                href={revisionsHref({ series: "UNRATE", period: "1990-01-01", asOf: parseAsOf("1995-06-01T09:30") ?? undefined })}
              >
                unemployment for January 1990, as of June 1, 1995
              </Link>
              .
            </CardDescription>
          </CardHeader>
        </Card>
      ) : !valid || !period ? (
        <Alert variant="warning">
          <TriangleAlertIcon />
          <AlertTitle>Check the series and period</AlertTitle>
          <AlertDescription>
            <p>Use a series ID such as UNRATE and a month such as January 1990.</p>
          </AlertDescription>
        </Alert>
      ) : all && !all.ok ? (
        <Alert variant="warning">
          <TriangleAlertIcon />
          <AlertTitle>Could not load the revisions</AlertTitle>
          <AlertDescription>
            <p>{failureText(all.failure)}</p>
          </AlertDescription>
        </Alert>
      ) : atMoment && !atMoment.ok ? (
        <Alert variant="warning">
          <TriangleAlertIcon />
          <AlertTitle>Could not load the value at that moment</AlertTitle>
          <AlertDescription>
            <p>{failureText(atMoment.failure)}</p>
          </AlertDescription>
        </Alert>
      ) : all && all.value.data.length === 0 ? (
        <Alert>
          <TriangleAlertIcon />
          <AlertTitle>
            No published values for {series}, {period}
          </AlertTitle>
          <AlertDescription>
            <p>{all.value.reason ?? "Our data has nothing for this series and month."}</p>
          </AlertDescription>
        </Alert>
      ) : all ? (
        <Results
          versions={all.value.data}
          known={atMoment ? atMoment.value.data : null}
          momentText={moment ? formatEtDateTime(moment) : null}
          backHref={moment ? `/time-machine?as_of=${toAsOfParam(moment)}` : "/time-machine"}
        />
      ) : null}
    </div>
  );
}

function Results({
  versions,
  known,
  momentText,
  backHref,
}: {
  versions: MacroObservation[];
  /** The versions public at the moment, or null when no moment was given. */
  known: MacroObservation[] | null;
  momentText: string | null;
  backHref: "/time-machine" | `/time-machine?${string}`;
}) {
  const knownKeys = new Set(known?.map(rowKey));
  const visible = known?.at(-1);
  const visibleKey = visible ? rowKey(visible) : null;

  const rows = versions.map((version, index) => {
    const key = rowKey(version);
    const status: Status =
      known === null ? "published" : key === visibleKey ? "visible" : knownKeys.has(key) ? "replaced" : "later";
    return { key, version, status, label: index === 0 ? "First release" : `Revision ${index}` };
  });

  const head = versions[0];
  const title = `${head.title}, ${formatPeriod(head.period, head.frequency)}`;
  const points: ChartPoint[] = rows.flatMap((row) =>
    row.version.value === null
      ? []
      : [
          {
            key: row.key,
            time: instantOf(row.version.available_at),
            value: row.version.value,
            valueText: formatMacroValue(row.version.value, row.version.units),
            dateText: dateText(row.version.available_at),
            status: row.status,
          },
        ],
  );

  let atMomentText: string | null = null;
  if (momentText) {
    atMomentText = visible
      ? `On ${momentText}, the value you could see was ${formatMacroValue(visible.value, visible.units)}.`
      : `Nothing had been published yet on ${momentText}.`;
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>
            {versions.length} published {versions.length === 1 ? "value" : "values"}, oldest first.
            {atMomentText ? ` ${atMomentText}` : " Add a Time Machine moment to see which one was visible then."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {points.length > 0 ? (
            <figure className="flex flex-col gap-2">
              <RevisionChart points={points} label={`${title}: ${points.map((p) => p.valueText).join(", then ")}`} />
              <figcaption className="text-xs text-muted-foreground">
                Time runs left to right. Solid dots were public at the moment. Hollow dashed dots
                were published later. The ring marks the value visible at the moment.
              </figcaption>
            </figure>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Table>
            <TableCaption>Every published version of {title}. Times are New York time.</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>Version</TableHead>
                <TableHead className="text-right">Value</TableHead>
                <TableHead>Became public</TableHead>
                <TableHead>Vintage</TableHead>
                {known ? <TableHead>At the moment</TableHead> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => {
                const when = etDateTimeOf(row.version.available_at);
                return (
                  <TableRow
                    key={row.key}
                    aria-current={row.status === "visible" ? "true" : undefined}
                    className={cn(row.status === "visible" && "bg-known/10", row.status === "later" && "bg-hatch-future")}
                  >
                    <TableCell className="font-medium">{row.label}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {formatMacroValue(row.version.value, row.version.units)}
                    </TableCell>
                    <TableCell className="font-mono text-xs tabular-nums">
                      {when ? formatEtDateTime(when) : row.version.available_at}
                      {row.version.time_assumed ? (
                        <span className="block text-muted-foreground">Time assumed: the source gave only the date.</span>
                      ) : null}
                    </TableCell>
                    <TableCell className="font-mono text-xs tabular-nums">{row.version.vintage_date}</TableCell>
                    {known ? (
                      <TableCell>
                        {row.status === "visible" ? (
                          <Badge variant="known">
                            <CheckIcon data-icon="inline-start" />
                            Visible then
                          </Badge>
                        ) : row.status === "later" ? (
                          <Badge variant="future">
                            <CircleDashedIcon data-icon="inline-start" />
                            Not yet known
                          </Badge>
                        ) : (
                          <Badge variant="outline">
                            <HistoryIcon data-icon="inline-start" />
                            Replaced by then
                          </Badge>
                        )}
                      </TableCell>
                    ) : null}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Button asChild variant="outline" className="w-fit">
        <Link href={backHref}>Back to the Time Machine</Link>
      </Button>
    </div>
  );
}