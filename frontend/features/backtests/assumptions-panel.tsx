import Link from "next/link";
import { BookOpenIcon } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { routes } from "@/config/navigation";
import { fixedAssumptions, specAssumptions } from "@/features/backtests/assumptions";
import type { BacktestRun } from "@/lib/api/types";

/**
 * What a run assumed, up front (S9.6, NFR-3): its decision time, fill rule, costs, and
 * delisting return, its benchmark and universe, the data version it read, and what every
 * run assumes.
 */
export function AssumptionsPanel({ run }: { run: BacktestRun }) {
  const rows: { term: string; detail: React.ReactNode }[] = [
    ...specAssumptions(run.spec),
    {
      term: "Data",
      detail: (
        <>
          Data version <code className="font-mono text-xs">{run.data_version}</code>, read as of
          each decision; engine <code className="font-mono text-xs">{run.engine_version}</code>
        </>
      ),
    },
  ];

  return (
    <Card id="assumptions">
      <CardHeader>
        <CardTitle>
          <h2>What the run assumed</h2>
        </CardTitle>
        <CardDescription>Every number on this page rests on these.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <dl className="grid grid-cols-1 gap-x-4 gap-y-2.5 sm:grid-cols-[6.5rem_1fr]">
          {rows.map((row) => (
            <div key={row.term} className="contents">
              <dt className="text-muted-foreground">{row.term}</dt>
              <dd className="min-w-0 text-pretty">{row.detail}</dd>
            </div>
          ))}
        </dl>
        <div className="flex flex-col gap-1.5">
          <h3 className="text-xs font-medium text-muted-foreground">And for every run</h3>
          <ul className="flex list-disc flex-col gap-1 pl-4 text-sm text-pretty text-muted-foreground marker:text-border">
            {fixedAssumptions(run.spec).map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        </div>
        <Link
          href={routes.methodology.href}
          className="inline-flex w-fit items-center gap-1.5 text-xs text-muted-foreground underline underline-offset-4 hover:text-brand-ink"
        >
          <BookOpenIcon aria-hidden className="size-3.5" />
          The timing rules and known limitations
        </Link>
      </CardContent>
    </Card>
  );
}
