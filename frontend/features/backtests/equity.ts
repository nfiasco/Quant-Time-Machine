import type { EquityPoint } from "@/lib/api/types";
import { formatPercent, formatUsd } from "@/lib/format";
import { formatEtShortDate, parseIsoDate } from "@/lib/time";

// A run's equity curve for its charts (S9.6): the growth of $1 in the portfolio beside the
// benchmark, and how far each had fallen from its peak. The API gives the curve, a point at
// the first fill and at each period's end (doc/reference/metrics.md, "The equity curve"),
// and leaves both drawdowns to be drawn from it (api-v1.md).

export type ChartPoint = {
  /** The session whose close the point is at: a fill, or the run's last close. */
  session: string;
  value: number;
  /** Null from the first period the benchmark had no return for. */
  benchmark: number | null;
  /** The fall from the highest value so far, from 1 at the first fill: −0.25 is a quarter. */
  drawdown: number;
  benchmarkDrawdown: number | null;
};

/** The curve's points with both drawdowns, as metrics.md defines the portfolio's. */
export function chartPoints(curve: readonly EquityPoint[]): ChartPoint[] {
  let peak = 1;
  let benchmarkPeak = 1;
  let benchmarkGone = false;
  return curve.map(({ at, value, benchmark }) => {
    peak = Math.max(peak, value);
    benchmarkGone ||= benchmark === null;
    let benchmarkDrawdown: number | null = null;
    if (!benchmarkGone && benchmark !== null) {
      benchmarkPeak = Math.max(benchmarkPeak, benchmark);
      benchmarkDrawdown = benchmark / benchmarkPeak - 1;
    }
    return {
      session: at.session,
      value,
      benchmark: benchmarkGone ? null : benchmark,
      drawdown: value / peak - 1,
      benchmarkDrawdown,
    };
  });
}

export type Trough = { depth: number; session: string };

/** The deepest point of a drawdown, at the first session it reached; null without one. */
export function deepest(
  points: readonly ChartPoint[],
  key: "drawdown" | "benchmarkDrawdown",
): Trough | null {
  let found: Trough | null = null;
  for (const point of points) {
    const depth = point[key];
    if (depth === null) continue;
    if (found === null || depth < found.depth) found = { depth, session: point.session };
  }
  return found;
}

/**
 * The sessions to label on the time axis: each year's first, or each month's for a run of
 * three years or less, thinned to at most `most` so they don't crowd.
 */
export function timeTicks(points: readonly ChartPoint[], most = 8): string[] {
  const sessions = points.map((point) => point.session);
  if (sessions.length === 0) return [];
  const span = Number(sessions.at(-1)!.slice(0, 4)) - Number(sessions[0].slice(0, 4));
  const byYear = span > 3;
  const firsts = sessions.filter(
    (session, index) =>
      index === 0 ||
      (byYear
        ? session.slice(0, 4) !== sessions[index - 1].slice(0, 4)
        : session.slice(0, 7) !== sessions[index - 1].slice(0, 7)),
  );
  const step = Math.ceil(firsts.length / most);
  return firsts.filter((_, index) => index % step === 0);
}

/** Even steps for the drawdown axis, the smallest that keeps it to six labels or fewer. */
const DRAWDOWN_STEPS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.25];

/**
 * The drawdown axis: from a round fall just below the deepest of both drawdowns to 0, in
 * even steps (0%, −5%, −10%, …), rather than from the deepest fall itself.
 */
export function drawdownScale(points: readonly ChartPoint[]): { floor: number; ticks: number[] } {
  const deepestFall = Math.min(
    0,
    ...points.map((point) => Math.min(point.drawdown, point.benchmarkDrawdown ?? 0)),
  );
  const step = DRAWDOWN_STEPS.find((size) => Math.ceil(-deepestFall / size - 1e-9) <= 6) ?? 0.25;
  const count = Math.max(1, Math.ceil(-deepestFall / step - 1e-9));
  const ticks = Array.from(
    { length: count + 1 },
    (_, index) => -Math.round((count - index) * step * 1e6) / 1e6 || 0,
  );
  return { floor: ticks[0], ticks };
}

/** Whether the axis labels years: a run of more than three years. */
export function ticksAreYears(ticks: readonly string[]): boolean {
  if (ticks.length < 2) return false;
  return Number(ticks.at(-1)!.slice(0, 4)) - Number(ticks[0].slice(0, 4)) > 3;
}

/**
 * The charts in a sentence or two, for screen readers and as their caption: where $1 ended
 * in the portfolio and in the benchmark, and each one's deepest fall.
 */
export function curveSummary(points: readonly ChartPoint[], benchmark: string): string {
  const first = points[0];
  const last = points.at(-1);
  if (!first || !last) return "The run has no equity curve.";
  const sentences = [
    `After costs, $1 in the portfolio at the close on ${day(first.session)} was worth ${formatUsd(last.value)} at the close on ${day(last.session)}` +
      (last.benchmark === null
        ? `; the benchmark, ${benchmark}, has gaps, so it isn't compared.`
        : `, and $1 in ${benchmark} was worth ${formatUsd(last.benchmark)}.`),
  ];
  const fall = deepest(points, "drawdown");
  const benchmarkFall = deepest(points, "benchmarkDrawdown");
  if (fall && fall.depth < 0) {
    sentences.push(
      `The portfolio's deepest fall from a peak was ${formatPercent(fall.depth)}, at the close on ${day(fall.session)}` +
        (benchmarkFall && benchmarkFall.depth < 0
          ? `; ${benchmark}'s was ${formatPercent(benchmarkFall.depth)}, on ${day(benchmarkFall.session)}.`
          : "."),
    );
  } else {
    sentences.push("The portfolio never fell below an earlier peak at a fill.");
  }
  return sentences.join(" ");
}

function day(session: string): string {
  const date = parseIsoDate(session);
  return date ? formatEtShortDate(date) : session;
}
