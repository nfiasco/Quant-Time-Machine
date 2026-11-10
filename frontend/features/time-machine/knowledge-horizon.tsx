import {
  CheckIcon,
  CircleDashedIcon,
  ExternalLinkIcon,
  TriangleAlertIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { MomentEvent } from "@/features/time-machine/moment-event";
import {
  formatEtDate,
  formatEtShortDate,
  formatEtTime,
  toAsOfParam,
  type EtDateTime,
} from "@/lib/time";
import { cn } from "@/lib/utils";

type KnowledgeHorizonProps = {
  /** The knowledge time T that splits the events. */
  moment: EtDateTime;
  /** Events in time order; `known` decides which side of T each lands on. */
  events: readonly MomentEvent[];
  /** Prefix for heading ids, so several horizons can share a page. */
  idPrefix?: string;
  /** Level of the two sides' headings: 3 on its own, 4 inside a card titled with an h3. */
  headingLevel?: 3 | 4;
  /** Shown on the known side when no event is known. */
  emptyKnown?: string;
  /** Shown on the not-yet-known side when no event is after T. */
  emptyNotYetKnown?: string;
  /** Show this many events per side and fold the rest into a "Show more" disclosure. */
  collapseAfter?: number;
  className?: string;
};

/**
 * The knowledge horizon: what was public at time T (solid, left or top) and what
 * wasn't yet (dashed, in hatched "fog", right or bottom). State is carried by
 * headings, icons, and borders as well as color. The two sides sit side by side when
 * the horizon's container is at least 36rem wide, and stack in a narrower one.
 */
export function KnowledgeHorizon({
  moment,
  events,
  idPrefix = "horizon",
  headingLevel = 3,
  emptyKnown = "Nothing in our data was public yet.",
  emptyNotYetKnown = "Nothing in our data became public later.",
  collapseAfter,
  className,
}: KnowledgeHorizonProps) {
  const known = events.filter((event) => event.known);
  const notYetKnown = events.filter((event) => !event.known);
  const Heading = headingLevel === 4 ? "h4" : "h3";

  return (
    <div className={cn("@container", className)}>
      <div className="grid gap-3 @xl:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] @xl:gap-0">
        <section
          aria-labelledby={`${idPrefix}-known`}
          className="flex flex-col gap-3 rounded-xl border border-known/20 bg-known/5 p-3"
        >
          <Heading id={`${idPrefix}-known`} className="flex flex-wrap items-center gap-2">
            <Badge variant="known">
              <CheckIcon data-icon="inline-start" />
              Known
            </Badge>
            <span className="text-xs text-muted-foreground">public at or before T</span>
          </Heading>
          <EventList events={known} empty={emptyKnown} collapseAfter={collapseAfter} />
        </section>

        {/* T, the knowledge time, wears the brand accent, as on the landing page's timeline. */}
        <div className="relative flex items-center justify-center py-1 @xl:px-4 @xl:py-0">
          <span
            aria-hidden
            className="absolute inset-x-0 top-1/2 border-t-2 border-primary @xl:inset-x-auto @xl:inset-y-0 @xl:top-0 @xl:left-1/2 @xl:-ml-px @xl:border-t-0 @xl:border-l-2"
          />
          <p className="relative flex flex-col items-center rounded-lg border border-primary/50 bg-background px-3 py-1.5 text-center shadow-xs">
            <span className="font-mono text-sm font-semibold text-brand-ink">
              T<span className="sr-only">, the knowledge time:</span>
            </span>
            <span className="text-xs whitespace-nowrap text-muted-foreground">
              {formatEtDate(moment)}
            </span>
            <span className="font-mono text-xs whitespace-nowrap tabular-nums">
              {formatEtTime(moment)}
            </span>
          </p>
        </div>

        <section
          aria-labelledby={`${idPrefix}-future`}
          className="flex flex-col gap-3 rounded-xl border border-dashed border-future/45 bg-hatch-future p-3"
        >
          <Heading id={`${idPrefix}-future`} className="flex flex-wrap items-center gap-2">
            <Badge variant="future">
              <CircleDashedIcon data-icon="inline-start" />
              Not yet known
            </Badge>
            <span className="text-xs text-muted-foreground">public after T</span>
          </Heading>
          <EventList
            events={notYetKnown}
            empty={emptyNotYetKnown}
            collapseAfter={collapseAfter}
          />
        </section>
      </div>
    </div>
  );
}

function EventList({
  events,
  empty,
  collapseAfter,
}: {
  events: readonly MomentEvent[];
  empty: string;
  collapseAfter?: number;
}) {
  if (events.length === 0) {
    return <p className="px-1 text-xs text-pretty text-muted-foreground">{empty}</p>;
  }

  // Folding a single event saves nothing, so fold only when two or more would hide.
  const fold = collapseAfter !== undefined && events.length > collapseAfter + 1;
  const shown = fold ? events.slice(0, collapseAfter) : events;
  const folded = fold ? events.slice(collapseAfter) : [];

  return (
    <>
      <ol className="flex flex-col gap-2">
        {shown.map((event) => (
          <EventItem key={event.id} event={event} />
        ))}
      </ol>
      {folded.length > 0 ? (
        <details>
          <summary className="w-fit cursor-pointer rounded-sm px-1 text-xs font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50">
            Show {folded.length} more
          </summary>
          <ol start={shown.length + 1} className="mt-2 flex flex-col gap-2">
            {folded.map((event) => (
              <EventItem key={event.id} event={event} />
            ))}
          </ol>
        </details>
      ) : null}
    </>
  );
}

function EventItem({ event }: { event: MomentEvent }) {
  const link = event.link?.href.startsWith("https://") ? event.link : undefined;

  return (
    <li
      className={cn(
        "flex flex-col gap-0.5 rounded-lg border bg-card px-3 py-2.5",
        !event.known && "border-dashed border-future/50",
      )}
    >
      <time
        dateTime={
          event.timeNote ? toAsOfParam(event.at).slice(0, 10) : toAsOfParam(event.at)
        }
        className={cn(
          "font-mono text-xs tabular-nums",
          event.known ? "text-known" : "text-future",
        )}
      >
        {formatEtShortDate(event.at)}
        {event.timeNote ? ` · ${event.timeNote}` : `, ${formatEtTime(event.at)}`}
      </time>
      <span className="font-medium text-pretty">{event.label}</span>
      {event.detail ? (
        <span className="text-xs text-pretty text-muted-foreground">{event.detail}</span>
      ) : null}
      {event.caveat ? (
        <span className="flex items-start gap-1 text-xs text-pretty text-muted-foreground">
          <TriangleAlertIcon aria-hidden className="mt-px size-3.5 shrink-0 text-brand-ink" />
          {event.caveat}
        </span>
      ) : null}
      {link ? (
        <a
          href={link.href}
          target="_blank"
          rel="noreferrer"
          className="mt-0.5 inline-flex w-fit items-center gap-1 rounded-sm text-xs font-medium text-brand-ink underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {link.label}
          <ExternalLinkIcon aria-hidden className="size-3" />
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
      ) : null}
    </li>
  );
}
