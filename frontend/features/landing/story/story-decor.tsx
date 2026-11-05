import { STORY_QUERY } from "./events";

/**
 * What the engine draws over the story: the stroke (logo, timeline, logo again) and its
 * arrowhead, the dashed "not yet known" continuation, two clocks, the date under the
 * clock, and the top bar with the knowledge time. Decoration only: everything here
 * repeats what the timeline's text already says, so it's hidden from assistive tech.
 */
export function StoryDecor() {
  return (
    <>
      <svg
        data-story-svg
        aria-hidden
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="pointer-events-none absolute inset-0 z-10 size-full overflow-visible text-foreground"
      >
        <g data-story-camera>
          <path
            data-story-future
            strokeWidth={1.5}
            strokeDasharray="1 7"
            className="text-muted-foreground"
          />
          <path data-story-snake strokeWidth={1.5} />
          <path data-story-chevron strokeWidth={1.5} />
          <Clock position="top" />
          <Clock position="bottom" />
        </g>
      </svg>
      {/* Timeline text fades out as it slides under the header and the top bar. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-25 h-32 bg-linear-to-b from-background from-55% to-transparent" />
      <p
        data-story-dial
        aria-hidden
        className="pointer-events-none absolute top-[calc(var(--story-anchor-y)+var(--story-r)*0.36)] left-1/2 z-10 -translate-x-1/2 font-mono text-xs tracking-wide whitespace-nowrap text-muted-foreground tabular-nums"
      />
      <div
        data-story-hud
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-[4.5rem] z-30 flex justify-center px-4"
      >
        <div className="flex max-w-full items-center gap-3 rounded-full border bg-background/90 px-4 py-1.5 font-mono text-xs shadow-xs">
          <span className="hidden truncate text-muted-foreground lg:inline">
            {STORY_QUERY.params}
          </span>
          <span className="hidden h-3 w-px bg-border lg:inline-block" />
          <span className="text-muted-foreground">Knowledge time</span>
          <span
            data-story-readout
            className="whitespace-nowrap tabular-nums data-[at-t=true]:text-brand-ink"
          />
        </div>
      </div>
    </>
  );
}

function Clock({ position }: { position: "top" | "bottom" }) {
  return (
    <g data-story-clock={position}>
      <line data-hand="hour" strokeWidth={2} />
      <line data-hand="minute" strokeWidth={1.5} />
      <circle r={2.5} fill="currentColor" stroke="none" />
    </g>
  );
}
