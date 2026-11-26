import { CircleCheckIcon, CircleMinusIcon, CircleAlertIcon, ExternalLinkIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { AuditGroupRow } from "@/features/backtests/audit";
import type { MemberRow, MemberStatus } from "@/features/backtests/members";
import { formatSignalValue, signalUnit } from "@/features/backtests/signal-values";
import type { ExperimentSpec } from "@/features/backtests/types";
import { formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_ICONS: Record<MemberStatus, typeof CircleCheckIcon> = {
  held: CircleCheckIcon,
  chosen: CircleAlertIcon,
  out: CircleMinusIcon,
};

/**
 * One rebalance's members (S9.6): what it held and at what weight, and why it passed over
 * the rest, with every signal's value and the newest filing the decision read for each
 * company. Eval task T5 is answered on Apple's row of June 1, 2020.
 */
export function MembersTable({
  rows,
  spec,
  filings,
}: {
  rows: readonly MemberRow[];
  spec: ExperimentSpec;
  /** The newest filing the decision read, by CIK (audit.ts, `newestFilings`). */
  filings: ReadonlyMap<string, AuditGroupRow>;
}) {
  const signalIds = Object.keys(spec.signals);
  const showFilings = filings.size > 0 && rows.some((row) => row.cik !== null);

  return (
    <Table className="min-w-[44rem]">
      <TableHeader>
        <TableRow>
          <TableHead scope="col">Member</TableHead>
          <TableHead scope="col">Held, or why not</TableHead>
          <TableHead scope="col" className="text-right">
            Weight (%)
          </TableHead>
          {signalIds.map((id) => {
            const unit = signalUnit(spec.signals[id]);
            return (
              <TableHead key={id} scope="col" className="text-right">
                <span className="font-mono">{id}</span>
                {unit ? <span className="font-normal text-muted-foreground"> ({unit})</span> : null}
              </TableHead>
            );
          })}
          <TableHead scope="col" className="text-right">
            Return (%)
          </TableHead>
          {showFilings ? <TableHead scope="col">Newest filing read</TableHead> : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const StatusIcon = STATUS_ICONS[row.status];
          const filing = row.cik === null ? undefined : filings.get(String(row.cik));
          return (
            <TableRow
              key={row.key}
              className={cn(row.status !== "held" && "text-muted-foreground")}
            >
              <TableHead scope="row" className="h-auto py-2 font-normal whitespace-normal">
                <span className="font-mono font-medium text-foreground">{row.ticker ?? "—"}</span>
                {row.name ? <span className="block text-xs">{row.name}</span> : null}
              </TableHead>
              <TableCell className="py-2 whitespace-normal">
                <Badge
                  variant={row.status === "held" ? "secondary" : "outline"}
                  className={cn(row.status === "chosen" && "border-primary/50")}
                >
                  <StatusIcon data-icon="inline-start" />
                  {row.label}
                </Badge>
                {row.detail ? (
                  <span className="mt-0.5 block max-w-xs text-xs text-pretty">{row.detail}</span>
                ) : null}
              </TableCell>
              <TableCell className="text-right align-top font-mono text-foreground tabular-nums">
                {row.weight === null ? "—" : formatPercent(row.weight)}
              </TableCell>
              {signalIds.map((id) => (
                <TableCell key={id} className="text-right align-top font-mono tabular-nums">
                  {formatSignalValue(row.signals[id], spec.signals[id])}
                </TableCell>
              ))}
              <TableCell className="text-right align-top font-mono tabular-nums">
                {row.periodReturn === null ? (
                  "—"
                ) : (
                  <span
                    className={cn(
                      row.periodReturn > 0 && "text-positive",
                      row.periodReturn < 0 && "text-negative",
                    )}
                  >
                    {formatPercent(row.periodReturn, { signed: true })}
                  </span>
                )}
                {row.valuedEarly ? (
                  <span className="block font-sans text-xs whitespace-normal text-muted-foreground">
                    {row.valuedEarly}
                  </span>
                ) : null}
              </TableCell>
              {showFilings ? (
                <TableCell className="align-top text-xs whitespace-normal">
                  {filing ? <FilingLink filing={filing} /> : "—"}
                </TableCell>
              ) : null}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

function FilingLink({ filing }: { filing: AuditGroupRow }) {
  const accession = <span className="font-mono">{filing.source.text}</span>;
  return (
    <span className="flex flex-col gap-0.5">
      {filing.source.href ? (
        <a
          href={filing.source.href}
          target="_blank"
          rel="noreferrer"
          className="inline-flex w-fit items-center gap-1 underline underline-offset-4 hover:text-brand-ink"
        >
          {accession}
          <ExternalLinkIcon aria-hidden className="size-3" />
          <span className="sr-only">(opens EDGAR)</span>
        </a>
      ) : (
        accession
      )}
      <span className="tabular-nums">public {filing.newest}</span>
    </span>
  );
}
