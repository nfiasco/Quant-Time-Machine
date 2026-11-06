import {
  LOGO_SWEEP,
  LOGO_VIEWBOX_SIZE,
  STORY_CHEVRON,
  UNIT_LOGO,
  chevronPath,
  chevronTransform,
  pointAt,
  snakePath,
} from "./story/geometry";

const half = LOGO_VIEWBOX_SIZE / 2;
const viewBox = `${-half} ${-half} ${LOGO_VIEWBOX_SIZE} ${LOGO_VIEWBOX_SIZE}`;
const arcPath = snakePath(0, LOGO_SWEEP, UNIT_LOGO);
const arrowTransform = chevronTransform(pointAt(LOGO_SWEEP, UNIT_LOGO));

/**
 * The large logo the story opens on, sized and placed by the story's CSS variables
 * (--story-r, --story-anchor-y). The scroll engine measures it to line up its own
 * drawing, so the hand-off is invisible.
 */
export function StoryLogo() {
  return (
    <svg
      data-story-logo
      viewBox={viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className="pointer-events-none absolute top-(--story-anchor-y) left-1/2 size-[calc(var(--story-r)*2.5)] -translate-x-1/2 -translate-y-1/2 overflow-visible text-foreground"
    >
      <path d={arcPath} vectorEffect="non-scaling-stroke" />
      <path
        d={chevronPath(UNIT_LOGO.r * STORY_CHEVRON)}
        transform={arrowTransform}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
