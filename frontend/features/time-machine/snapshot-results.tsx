import { CodeIcon, DatabaseIcon, EyeOffIcon, TriangleAlertIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CopyLinkButton } from "@/features/time-machine/copy-link-button";
import { KnowledgeHorizon } from "@/features/time-machine/knowledge-horizon";
import type { EntityHorizon, SnapshotView } from "@/features/time-machine/snapshot-events";
import { formatEtDateTime, type EtDateTime } from "@/lib/time";

type SnapshotResultsProps = {
  view: SnapshotView;
  /** The view's own link, for the copy button. */
  href: string;
  /** The API request behind it, for readers who want the evidence. */
  requestUrl: string;
};

/** A snapshot: one knowledge horizon per company and per series, split at T. */
export function SnapshotResults({ view, href, requestUrl }: SnapshotResultsProps) {
  const moment = formatEtDateTime(view.knowledgeTime);
  const counts = [
    plural(view.companies.length, "company", "companies"),
    plural(view.series.length, "series", "series"),
  ].join(" and ");

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="snapshot-heading" className="flex flex-col gap-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 flex-col gap-1">
            <h2 id="snapshot-heading" className="text-base font-semibold text-pretty">
              What was known at {moment}
            </h2>
            <p className="text-xs text-muted-foreground">
              {counts} · data version{" "}
              <span className="font-mono tabular-nums">{view.dataVersion ?? "none yet"}</span>
            </p>
          </div>
          <CopyLinkButton href={href} />
        </div>

        <p className="max-w-3xl text-sm text-pretty text-muted-foreground">
          <strong className="font-medium text-foreground">Known</strong> means public at or
          before T. <strong className="font-medium text-foreground">Not yet known</strong>{" "}
          lists what our data shows became public after T: the next close, the next filing
          of each form, amendments, and later versions of the values shown, but not new
          periods.
        </p>

        {view.pricesWithheld ? (
          <Alert variant="info" role="note">
            <EyeOffIcon />
            <AlertTitle>Prices are withheld on this server</AlertTitle>
            <AlertDescription>
              Our price source&apos;s terms don&apos;t cover showing raw prices yet
              (decision D2), so each close shows when it became known, without the price.
            </AlertDescription>
          </Alert>
        ) : null}

        {view.afterDataCut ? (
          <Alert variant="info" role="note">
            <DatabaseIcon />
            <AlertTitle>This moment is after our data was last updated</AlertTitle>
            <AlertDescription>
              {view.dataCut
                ? `Data version ${view.dataVersion} was cut at ${formatEtDateTime(view.dataCut)}, `
                : "Our data was cut before this moment, "}
              so nothing can show as not yet known.
            </AlertDescription>
          </Alert>
        ) : null}

        {view.hidden > 0 ? (
          <Alert variant="warning" role="note">
            <TriangleAlertIcon />
            <AlertTitle>
              {plural(view.hidden, "record", "records")} left out
            </AlertTitle>
            <AlertDescription>
              {view.hidden === 1 ? "Its time contradicts" : "Their times contradict"} the
              side of T the API put {view.hidden === 1 ? "it" : "them"} on. Rather than risk
              showing a later record as known, the page leaves{" "}
              {view.hidden === 1 ? "it" : "them"} out. Please report it.
            </AlertDescription>
          </Alert>
        ) : null}

        <details className="text-xs text-muted-foreground">
          <summary className="flex w-fit cursor-pointer items-center gap-1.5 rounded-sm font-medium outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50">
            <CodeIcon aria-hidden className="size-3.5" />
            The API request behind this view
          </summary>
          <p className="mt-2 text-pretty">
            Everything here comes from one call to the research API (
            <code className="font-mono">GET /v1/snapshot</code>). Open it to see the JSON:
          </p>
          <a
            href={requestUrl}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-block rounded-sm font-mono break-all text-brand-ink underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            {requestUrl}
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        </details>
      </section>

      {view.companies.length > 0 ? (
        <EntitySection
          id="companies"
          title="Companies"
          entities={view.companies}
          moment={view.knowledgeTime}
        />
      ) : null}
      {view.series.length > 0 ? (
        <EntitySection
          id="series"
          title="Economic series"
          entities={view.series}
          moment={view.knowledgeTime}
        />
      ) : null}
    </div>
  );
}

function EntitySection({
  id,
  title,
  entities,
  moment,
}: {
  id: string;
  title: string;
  entities: EntityHorizon[];
  moment: EtDateTime;
}) {
  return (
    <section aria-labelledby={`${id}-heading`} className="flex flex-col gap-3">
      <h2 id={`${id}-heading`} className="text-base font-semibold">
        {title}
      </h2>
      <ul className="flex flex-col gap-4">
        {entities.map((entity) => (
          <li key={entity.key}>
            <EntityCard entity={entity} moment={moment} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function EntityCard({ entity, moment }: { entity: EntityHorizon; moment: EtDateTime }) {
  return (
    <Card id={entity.key} size="sm" className="scroll-mt-20">
      <CardHeader>
        <CardTitle>
          <h3 className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-mono font-semibold">{entity.code}</span>
            {entity.name !== entity.code ? <span>{entity.name}</span> : null}
          </h3>
        </CardTitle>
        {entity.facts.length > 0 ? (
          <CardDescription className="text-xs">{entity.facts.join(" · ")}</CardDescription>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <KnowledgeHorizon
          moment={moment}
          events={entity.events}
          idPrefix={entity.key}
          headingLevel={4}
          emptyKnown={entity.emptyKnown}
          emptyNotYetKnown={entity.emptyNotYetKnown}
          collapseAfter={5}
        />
        {entity.missing.length > 0 ? (
          <p className="text-xs text-pretty text-muted-foreground">
            Not in our data by T: {entity.missing.join(", ")}.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}
