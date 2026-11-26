import { CheckIcon, ExternalLinkIcon, OctagonAlertIcon } from "lucide-react";

import { KnowledgeTimeLabel } from "@/components/knowledge/knowledge-time-label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { AuditGroupRow, AuditSection } from "@/features/backtests/audit";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * The audit drill-down (S9.6): for each view a rebalance opened, its knowledge time T,
 * every table it read with when its earliest and newest rows became public, and, one step
 * away, each company's or series' newest source. In the knowledge horizon's language
 * (GUIDELINES.md §2): T in amber, and what was known at T solid.
 */
export function AuditPanel({ sections }: { sections: readonly AuditSection[] }) {
  return (
    <div className="flex flex-col gap-6">
      {sections.map((section) => (
        <section
          key={section.purpose}
          aria-labelledby={`audit-${section.purpose}`}
          className="flex flex-col gap-3"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
            {section.moment ? (
              <KnowledgeTimeLabel moment={section.moment} className="w-fit shrink-0" />
            ) : null}
            <div className="flex flex-col gap-1.5">
              <h4 id={`audit-${section.purpose}`} className="font-medium">
                {section.title}
              </h4>
              <p className="text-xs text-pretty text-muted-foreground">{section.description}</p>
              {section.allKnown ? (
                <p className="flex flex-wrap items-center gap-2 text-sm">
                  <Badge variant="known">
                    <CheckIcon data-icon="inline-start" />
                    Known
                  </Badge>
                  All {formatNumber(section.rows)} rows were public at or before T,{" "}
                  {section.knowledgeTime}.
                </p>
              ) : (
                <Alert variant="destructive">
                  <OctagonAlertIcon />
                  <AlertTitle>A table read something dated after T</AlertTitle>
                  <AlertDescription>
                    Its newest row became public after {section.knowledgeTime}, which no view should
                    return. The table is marked below.
                  </AlertDescription>
                </Alert>
              )}
            </div>
          </div>

          <ul className="flex flex-col gap-2">
            {section.tables.map((table) => (
              <li key={table.table}>
                <details
                  className={cn(
                    "group/table rounded-lg border",
                    table.known
                      ? "border-known/20 bg-known/5"
                      : "border-destructive/50 bg-destructive/5",
                  )}
                >
                  <summary className="flex cursor-pointer flex-wrap items-baseline justify-between gap-x-3 gap-y-1 rounded-lg px-3 py-2 select-none hover:bg-muted/40 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none">
                    <span className="min-w-0">
                      <span className="font-medium">{table.title}</span>{" "}
                      <span className="text-xs text-muted-foreground">{table.description}</span>
                    </span>
                    <span className="font-mono text-xs text-muted-foreground tabular-nums">
                      {formatNumber(table.rows)} {table.rows === 1 ? "row" : "rows"} ·{" "}
                      {formatNumber(table.groups.length)}{" "}
                      {table.groups.length === 1 ? "group" : "groups"} · newest {table.newest}
                      {table.known ? null : (
                        <span className="ml-1 font-sans font-medium text-destructive">after T</span>
                      )}
                    </span>
                  </summary>
                  <div className="flex flex-col gap-2 border-t px-3 py-2">
                    <p className="text-xs text-muted-foreground">
                      Its rows became public from {table.earliest} to {table.newest}.
                    </p>
                    <div className="max-h-80 overflow-y-auto">
                      <GroupTable groups={table.groups} />
                    </div>
                  </div>
                </details>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function GroupTable({ groups }: { groups: readonly AuditGroupRow[] }) {
  return (
    <Table className="min-w-[34rem]">
      <TableHeader>
        <TableRow>
          <TableHead scope="col">Read for</TableHead>
          <TableHead scope="col" className="text-right">
            Rows
          </TableHead>
          <TableHead scope="col">Newest public (ET)</TableHead>
          <TableHead scope="col">Newest source</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {groups.map((group) => (
          <TableRow key={group.key}>
            <TableHead scope="row" className="h-auto py-1.5 font-normal whitespace-normal">
              <span className={cn(group.isKey && "font-mono text-xs")}>{group.label}</span>
              {group.detail ? (
                <span className="block font-mono text-xs text-muted-foreground">
                  {group.detail}
                </span>
              ) : null}
            </TableHead>
            <TableCell className="text-right font-mono text-xs tabular-nums">
              {formatNumber(group.rows)}
            </TableCell>
            <TableCell className="text-xs tabular-nums">
              {group.newest}
              {group.known ? null : (
                <span className="ml-1 font-medium text-destructive">after T</span>
              )}
            </TableCell>
            <TableCell className="max-w-64 truncate text-xs">
              {group.source.href ? (
                <a
                  href={group.source.href}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 underline underline-offset-4 hover:text-brand-ink"
                >
                  <span className="font-mono">{group.source.text}</span>
                  <ExternalLinkIcon aria-hidden className="size-3 shrink-0" />
                  <span className="sr-only">(opens in a new tab)</span>
                </a>
              ) : (
                <span className="font-mono">{group.source.text}</span>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
