import { CheckIcon, CircleDashedIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { MomentEvent } from "@/features/time-machine/example-moment";
import { formatEtDate, formatEtTime, type EtDateTime } from "@/lib/time";
import { cn } from "@/lib/utils";

type KnowledgeHorizonProps = {
  /** The knowledge time T that splits the events. */
  moment: EtDateTime;
  /** Events in time order; `known` decides which side of T each lands on. */
  events: readonly MomentEvent[];
  /** Prefix for heading ids, so two horizons can share a page. */
  idPrefix?: string;
  className?: string;
};

/**
 * The knowledge horizon: what was public at time T (solid, left or top) and what
 * wasn't yet (dashed, in hatched "fog", right or bottom). State is carried by
 * headings, icons, and borders as well as color.
 */
export function KnowledgeHorizon({
  moment,
  events,
  idPrefix = "horizon",
  className,
}: KnowledgeHorizonProps) {
  const known = events.filter((event) => event.known);
  const notYetKnown = events.filter((event) => !event.known);

  return (
    <div
      className={cn(
        "grid gap-3 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] md:gap-0",
        className,
      )}
    >
      <section
        aria-labelledby={`${idPrefix}-known`}
        className="flex flex-col gap-3 rounded-xl border border-known/20 bg-known/5 p-3"
      >
        <h3 id={`${idPrefix}-known`} className="flex flex-wrap items-center gap-2">
          <Badge variant="known">
            <CheckIcon data-icon="inline-start" />
            Known
          </Badge>
          <span className="text-xs text-muted-foreground">public at or before T</span>
        </h3>
        <EventList events={known} />
      </section>

      <div className="relative flex items-center justify-center py-1 md:px-4 md:py-0">
        <span
          aria-hidden
          className="absolute inset-x-0 top-1/2 border-t-2 border-foreground/60 md:inset-x-auto md:inset-y-0 md:top-0 md:left-1/2 md:-ml-px md:border-t-0 md:border-l-2"
        />
        <p className="relative flex flex-col items-center rounded-lg border bg-background px-3 py-1.5 text-center shadow-xs">
          <span className="font-mono text-sm font-semibold">
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
        <h3 id={`${idPrefix}-future`} className="flex flex-wrap items-center gap-2">
          <Badge variant="future">
            <CircleDashedIcon data-icon="inline-start" />
            Not yet known
          </Badge>
          <span className="text-xs text-muted-foreground">public after T</span>
        </h3>
        <EventList events={notYetKnown} />
      </section>
    </div>
  );
}

function EventList({ events }: { events: readonly MomentEvent[] }) {
  return (
    <ol className="flex flex-col gap-2">
      {events.map((event) => (
        <li
          key={event.id}
          className={cn(
            "flex flex-col gap-0.5 rounded-lg border bg-card px-3 py-2.5",
            !event.known && "border-dashed border-future/50",
          )}
        >
          <span
            className={cn(
              "font-mono text-xs tabular-nums",
              event.known ? "text-known" : "text-future",
            )}
          >
            {event.when}
          </span>
          <span className="font-medium text-pretty">{event.label}</span>
          <span className="text-xs text-pretty text-muted-foreground">{event.detail}</span>
        </li>
      ))}
    </ol>
  );
}
