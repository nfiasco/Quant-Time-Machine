// Geometry of the logo stroke: pure functions, no DOM. The server draws the static logo
// with them and the scroll engine draws every frame of the story with them, so the two
// always match. SVG's y axis points down.
//
// The stroke is one path, measured by a coordinate q:
//   q in [0, 1]                      top circle, centered on (cx, 0): from 9 o'clock,
//                                    counter-clockwise, one full turn
//   q in [1, 1 + S]                  the timeline, x = cx − r, through the slot
//                                    positions y = slots[0..S], where slots[0] is 0
//   q in [1 + S, 1 + S + LOGO_SWEEP] bottom circle, centered on (cx, slots[S]),
//                                    entered at its 9 o'clock
// The line is tangent to both circles at 9 o'clock, so both joins are seamless.

/** How far round the logo's arc goes: 11/12 of a turn, leaving the gap its arrowhead points into. */
export const LOGO_SWEEP = 11 / 12;

/** The logo drawn at radius 100 fills this square viewBox, centered on the circle. */
export const LOGO_VIEWBOX_SIZE = 250;

/** The story's arrowhead arm length, as a fraction of the circle's radius. */
export const STORY_CHEVRON = 0.075;

export type StrokeLayout = {
  /** x of both circle centers. */
  cx: number;
  r: number;
  /** World y of each slot on the line, increasing; slots[0] is 0. */
  slots: readonly number[];
};

export type StrokePoint = {
  x: number;
  y: number;
  /** Direction of travel in degrees, for SVG's rotate(): 0 is right, 90 is down. */
  angle: number;
};

/** The logo on its own, at radius 100, centered on (0, 0). */
export const UNIT_LOGO: StrokeLayout = { cx: 0, r: 100, slots: [0] };

/** Where the line ends and the bottom circle begins. */
export function lineEnd(layout: StrokeLayout): number {
  return layout.slots.length;
}

/** y on the line at slot position `s`; fractional positions interpolate. */
export function lineY(s: number, layout: StrokeLayout): number {
  const { slots } = layout;
  const last = slots.length - 1;
  if (s <= 0) return slots[0];
  if (s >= last) return slots[last];
  const i = Math.floor(s);
  return slots[i] + (slots[i + 1] - slots[i]) * (s - i);
}

/** The q of the point on the line at world height `y`, clamped to the line. */
export function lineQAtY(y: number, layout: StrokeLayout): number {
  const { slots } = layout;
  const last = slots.length - 1;
  if (y <= slots[0]) return 1;
  if (y >= slots[last]) return 1 + last;
  let i = 0;
  while (i < last - 1 && slots[i + 1] < y) i++;
  const span = slots[i + 1] - slots[i];
  return 1 + i + (span > 0 ? (y - slots[i]) / span : 0);
}

function circlePoint(cx: number, cy: number, r: number, turn: number): StrokePoint {
  // θ is measured counter-clockwise on screen from 3 o'clock; turn 0 is 9 o'clock.
  const theta = Math.PI + 2 * Math.PI * turn;
  return {
    x: cx + r * Math.cos(theta),
    y: cy - r * Math.sin(theta),
    // Travel direction (−sin θ, −cos θ), as an angle on the y-down screen.
    angle: (Math.atan2(-Math.cos(theta), -Math.sin(theta)) * 180) / Math.PI,
  };
}

export function pointAt(q: number, layout: StrokeLayout): StrokePoint {
  const end = lineEnd(layout);
  if (q <= 1) return circlePoint(layout.cx, 0, layout.r, q);
  if (q >= end) {
    return circlePoint(layout.cx, lineY(end - 1, layout), layout.r, q - end);
  }
  return { x: layout.cx - layout.r, y: lineY(q - 1, layout), angle: 90 };
}

const round = (v: number) => Math.round(v * 10) / 10;

/** Counter-clockwise arc commands from `from` to `to` turns, in pieces of at most 90°. */
function arc(cx: number, cy: number, r: number, from: number, to: number): string {
  if (to - from < 1e-6) return "";
  const pieces = Math.ceil((to - from) / 0.25 - 1e-9);
  let d = "";
  for (let i = 1; i <= pieces; i++) {
    const p = circlePoint(cx, cy, r, from + ((to - from) * i) / pieces);
    // Sweep flag 0 is counter-clockwise on a y-down screen. Each piece is under 180°,
    // so the large-arc flag stays 0; a single command can't draw a full turn.
    d += ` A${round(r)} ${round(r)} 0 0 0 ${round(p.x)} ${round(p.y)}`;
  }
  return d;
}

/** The visible stroke between `tail` and `head`, as an SVG path. */
export function snakePath(tail: number, head: number, layout: StrokeLayout): string {
  if (head - tail < 1e-4) return "";
  const end = lineEnd(layout);
  const start = pointAt(tail, layout);
  let d = `M${round(start.x)} ${round(start.y)}`;
  if (tail < 1) d += arc(layout.cx, 0, layout.r, tail, Math.min(head, 1));
  if (head > 1 && tail < end) {
    d += ` L${round(layout.cx - layout.r)} ${round(lineY(Math.min(head, end) - 1, layout))}`;
  }
  if (head > end) {
    const cy = lineY(end - 1, layout);
    d += arc(layout.cx, cy, layout.r, Math.max(tail, end) - end, head - end);
  }
  return d;
}

/** A right-angled chevron pointing along +x, its tip at the origin. */
export function chevronPath(size: number): string {
  return `M${round(-size)} ${round(-size)} L0 0 L${round(-size)} ${round(size)}`;
}

/** Places the chevron's tip on a point, pointing along the stroke. */
export function chevronTransform(point: StrokePoint): string {
  return `translate(${round(point.x)} ${round(point.y)}) rotate(${round(point.angle)})`;
}
