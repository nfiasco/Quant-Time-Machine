import { Badge } from "@/components/ui/badge";
import {
  formatEtDateTime,
  formatEtShortDate,
  formatEtTime,
} from "@/lib/time";
import { cn } from "@/lib/utils";

import { SLOT } from "./beats";
import {
  KNOWLEDGE_TIME,
  KNOWLEDGE_TIME_ISO,
  SNAPSHOT_KNOWN,
  STORY_LATER,
  STORY_STOPS,
  type StoryEvent,
} from "./events";

// Static layout: a vertical list with its own line, drawn per item. Animated layout
// (story-animated:): each item is placed on the engine's line by --line-x and --y, and
// the engine draws the line, so the per-item segments hide.
const itemBase = cn(
  "group/stop relative ml-3 pb-16 pl-8 md:ml-52",
  "before:absolute before:top-3 before:bottom-0 before:left-0 before:w-px before:-translate-x-1/2",
  "story-animated:absolute story-animated:top-0 story-animated:left-(--line-x) story-animated:ml-0 story-animated:pb-0",
  "story-animated:w-[min(34rem,calc(100%-var(--line-x)-1.25rem))] story-animated:translate-y-(--y) story-animated:before:hidden",
);

const solidSegment = "before:bg-foreground";
const dashedSegment =
  "before:w-0 before:border-l before:border-dashed before:border-muted-foreground";

// A stop the arrow hasn't reached yet is faint. It's set per child, not on the item:
// the engine fades whole items, and a filter on a wrapper would move the date column.
const pendingFade =
  "transition-[opacity,filter] duration-300 group-data-[state=pending]/stop:opacity-55 md:group-data-[state=pending]/stop:blur-[1.5px]";

/**
 * What became public, in order: six stops before the knowledge time, the knowledge
 * time with the snapshot it returns, then three facts that came later. The server
 * renders the truth; in the animated story, stops start "not yet known" and flip as
 * the arrow reaches them.
 */
export function StoryTimeline() {
  return (
    <ol
      aria-label="What became public, in order"
      className="mx-auto max-w-2xl px-6 pb-8 md:max-w-4xl story-animated:m-0 story-animated:max-w-none story-animated:p-0"
    >
      {STORY_STOPS.map((event, index) => (
        <TimelineEvent
          key={event.id}
          event={event}
          slot={SLOT.firstStop + index}
        />
      ))}
      <KnowledgeTimeRow />
      {STORY_LATER.map((event, index) => (
        <TimelineEvent
          key={event.id}
          event={event}
          slot={SLOT.firstLater + index}
          last={index === STORY_LATER.length - 1}
        />
      ))}
    </ol>
  );
}

function TimelineEvent({
  event,
  slot,
  last = false,
}: {
  event: StoryEvent;
  slot: number;
  last?: boolean;
}) {
  const later = event.kind === "later";

  return (
    <li
      data-stop={slot}
      data-kind={event.kind}
      data-state={event.kind}
      className={cn(
        itemBase,
        later ? dashedSegment : solidSegment,
        later && "pb-10",
        last && "before:hidden",
      )}
    >
      <Marker kind={event.kind} />
      <p
        className={cn(
          "font-mono text-xs text-muted-foreground tabular-nums md:absolute md:top-0.5 md:right-full md:mr-10 md:w-44 md:text-right",
          pendingFade,
        )}
      >
        <time dateTime={event.iso}>
          <span>{formatEtShortDate(event.at)}</span>
          <span className="md:hidden"> · </span>
          <span className="md:block">{event.timeNote ?? formatEtTime(event.at)}</span>
        </time>
      </p>
      <h3
        className={cn(
          "mt-1 text-lg font-semibold tracking-tight text-balance md:mt-0",
          pendingFade,
        )}
      >
        {event.title}
      </h3>
      {event.value ? (
        <p
          className={cn(
            "mt-1 font-mono text-2xl font-medium tracking-tight tabular-nums",
            pendingFade,
          )}
        >
          {event.value}
        </p>
      ) : null}
      <p
        className={cn(
          "mt-2 max-w-prose text-sm text-pretty text-muted-foreground",
          pendingFade,
        )}
      >
        {event.detail}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
        <StateBadge kind={event.kind} />
        <span className="font-mono text-xs text-muted-foreground">
          {event.lesson}
        </span>
      </div>
    </li>
  );
}

/** The tick on the line. Filled: known. Hollow: not yet known. Square: a period end. */
function Marker({ kind }: { kind: StoryEvent["kind"] }) {
  return (
    <span
      aria-hidden
      data-marker
      className={cn(
        "absolute top-1.5 left-0 z-10 size-3 -translate-x-1/2 ring-4 ring-background",
        kind === "known" &&
          "rounded-full bg-foreground group-data-[state=pending]/stop:border group-data-[state=pending]/stop:border-foreground group-data-[state=pending]/stop:bg-background",
        kind === "period" &&
          "rounded-[3px] border border-muted-foreground bg-background",
        kind === "later" &&
          "rounded-full border border-dashed border-muted-foreground bg-background",
      )}
    />
  );
}

function StateBadge({ kind }: { kind: StoryEvent["kind"] }) {
  if (kind === "period") {
    return <Badge variant="outline">Period end, not a publication</Badge>;
  }
  if (kind === "later") {
    return <Badge variant="future">Not yet known</Badge>;
  }
  return (
    <>
      <Badge variant="known" className="group-data-[state=pending]/stop:hidden">
        Known
      </Badge>
      <Badge
        variant="future"
        className="hidden group-data-[state=pending]/stop:inline-flex"
      >
        Not yet known
      </Badge>
    </>
  );
}

/** T: the line between what was public and what wasn't, with the snapshot it returns. */
function KnowledgeTimeRow() {
  return (
    <li
      data-stop={SLOT.horizon}
      data-kind="horizon"
      className={cn(itemBase, dashedSegment, "pb-12 before:top-0")}
    >
      <span
        aria-hidden
        className="absolute top-0 -right-2 left-0 h-px bg-brand-ink/60 md:-left-52"
      />
      <span
        aria-hidden
        data-marker
        className="absolute top-0 left-0 z-10 size-3.5 -translate-x-1/2 -translate-y-1/2 rotate-45 rounded-[3px] bg-primary ring-4 ring-background"
      />
      <div className="pt-4">
        <p className="font-mono text-xs text-brand-ink tabular-nums md:absolute md:top-4 md:right-full md:mr-10 md:w-44 md:text-right">
          <time dateTime={KNOWLEDGE_TIME_ISO}>
            <span>{formatEtShortDate(KNOWLEDGE_TIME)}</span>
            <span className="md:hidden"> · </span>
            <span className="md:block">{formatEtTime(KNOWLEDGE_TIME)}</span>
          </time>
        </p>
        <h3 className="mt-1 text-lg font-semibold tracking-tight md:mt-0">
          Knowledge time
        </h3>
        <p className="mt-1 text-sm text-pretty text-muted-foreground">
          Everything above this line was public. Nothing below it was.
        </p>
        <SnapshotCard />
      </div>
    </li>
  );
}

function SnapshotCard() {
  return (
    <div className="mt-5 max-w-md rounded-2xl border bg-card p-5 text-card-foreground shadow-xs">
      <p className="font-mono text-xs text-muted-foreground">
        Snapshot · {formatEtDateTime(KNOWLEDGE_TIME)}
      </p>
      <h4 className="mt-1 font-semibold">What was known</h4>
      <dl className="mt-3 divide-y">
        {SNAPSHOT_KNOWN.map((row) => (
          <div
            key={row.label}
            className="flex items-baseline justify-between gap-4 py-2.5"
          >
            <dt className="min-w-0">
              <span className="block text-sm">{row.label}</span>
              <span className="block font-mono text-xs text-muted-foreground">
                {row.at
                  ? `Public ${formatEtShortDate(row.at)}, ${formatEtTime(row.at)}`
                  : row.note}
              </span>
            </dt>
            <dd className="shrink-0 text-right font-mono text-sm font-medium tabular-nums">
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 border-t border-dashed pt-3 text-xs text-pretty text-muted-foreground">
        Withheld: {STORY_LATER.length} later facts, public only after 9:30 AM ET.
      </p>
    </div>
  );
}
