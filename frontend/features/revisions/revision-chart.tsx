export type ChartPoint = {
  key: string;
  /** When this version became public, in milliseconds since the epoch. */
  time: number;
  value: number;
  /** The value as text, such as "5.3%". */
  valueText: string;
  /** The date it became public, such as "Feb 2, 1990". */
  dateText: string;
  status: "visible" | "replaced" | "later" | "published";
};

const WIDTH = 560;
const HEIGHT = 240;
const PAD = { left: 48, right: 48, top: 36, bottom: 48 };

/**
 * Every published value of one observation as a step chart on a time axis: each version
 * holds until the next one is published. Solid = public by the Time Machine's moment,
 * dashed and hollow = published later, ring = the value visible at that moment.
 */
export function RevisionChart({ points, label }: { points: ChartPoint[]; label: string }) {
  const times = points.map((p) => p.time);
  const values = points.map((p) => p.value);
  const t0 = Math.min(...times);
  const t1 = Math.max(...times);
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (lo === hi) {
    lo -= 0.5;
    hi += 0.5;
  } else {
    const margin = (hi - lo) * 0.3;
    lo -= margin;
    hi += margin;
  }

  const plotWidth = WIDTH - PAD.left - PAD.right;
  const x = (t: number) => (t1 === t0 ? PAD.left + plotWidth / 2 : PAD.left + ((t - t0) / (t1 - t0)) * plotWidth);
  const y = (v: number) => PAD.top + (1 - (v - lo) / (hi - lo)) * (HEIGHT - PAD.top - PAD.bottom);
  const axisY = HEIGHT - PAD.bottom;

  const first = points[0];
  const last = points[points.length - 1];

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={label} className="h-auto w-full">
      <line x1={PAD.left} x2={WIDTH - PAD.right} y1={axisY} y2={axisY} className="stroke-border" />

      {points.slice(1).map((point, index) => {
        const previous = points[index];
        return (
          <path
            key={`step-${point.key}`}
            d={`M ${x(previous.time)} ${y(previous.value)} H ${x(point.time)} V ${y(point.value)}`}
            fill="none"
            strokeWidth={2}
            strokeDasharray={point.status === "later" ? "5 4" : undefined}
            className={point.status === "later" ? "stroke-future" : "stroke-known"}
          />
        );
      })}

      {points.map((point) => (
        <g key={point.key}>
          {point.status === "visible" ? (
            <circle cx={x(point.time)} cy={y(point.value)} r={10} fill="none" strokeWidth={2.5} className="stroke-primary" />
          ) : null}
          <circle
            cx={x(point.time)}
            cy={y(point.value)}
            r={5}
            strokeWidth={2}
            strokeDasharray={point.status === "later" ? "3 2" : undefined}
            className={point.status === "later" ? "fill-card stroke-future" : "fill-known stroke-known"}
          />
          <text
            x={x(point.time)}
            y={y(point.value) - 16}
            textAnchor={x(point.time) < PAD.left + 24 ? "start" : x(point.time) > WIDTH - PAD.right - 24 ? "end" : "middle"}
            className="fill-foreground text-xs font-medium"
          >
            {point.valueText}
          </text>
        </g>
      ))}

      <text x={x(first.time)} y={axisY + 20} textAnchor={first === last ? "middle" : "start"} className="fill-muted-foreground text-xs">
        {first.dateText}
      </text>
      {first === last ? null : (
        <text x={x(last.time)} y={axisY + 20} textAnchor="end" className="fill-muted-foreground text-xs">
          {last.dateText}
        </text>
      )}
    </svg>
  );
}