import { cn } from "@/lib/utils";

// The logo at radius 100, centered on (0, 0): an arc from 9 o'clock round 11/12 of a
// turn counter-clockwise, and a chevron at its end pointing back toward its start.
// Generated from features/landing/story/geometry.ts (snakePath and chevronTransform
// with LOGO_SWEEP), so the mark matches the landing page's scroll story and
// app/icon.svg exactly.
const ARC =
  "M-100 0 A100 100 0 0 0 -13.1 99.1 A100 100 0 0 0 96.6 25.9 A100 100 0 0 0 38.3 -92.4 A100 100 0 0 0 -86.6 -50";
const ARROWHEAD = "M-38 -38 L0 0 L-38 38";
const ARROWHEAD_TRANSFORM = "translate(-86.6 -50) rotate(120)";

/**
 * The brand mark: a circle that runs counter-clockwise into a golden arrowhead, like
 * lucide's RotateCcw. The circle takes the text color, so it follows the theme; the
 * arrowhead is the brand amber in both. Decorative; pair it with the product name.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="-125 -125 250 250"
      fill="none"
      stroke="currentColor"
      strokeWidth={22}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={cn("size-6 shrink-0", className)}
    >
      <path d={ARC} />
      <path
        d={ARROWHEAD}
        transform={ARROWHEAD_TRANSFORM}
        className="stroke-primary"
      />
    </svg>
  );
}
