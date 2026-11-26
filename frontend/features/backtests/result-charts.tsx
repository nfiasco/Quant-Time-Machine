"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  XAxis,
  YAxis,
} from "recharts";

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import type { ChartPoint } from "@/features/backtests/equity";
import { formatPercent, formatUsd } from "@/lib/format";
import { formatEtMonth, formatEtShortDate, parseIsoDate } from "@/lib/time";

type ResultChartsProps = {
  points: ChartPoint[];
  /** The benchmark's ticker, such as SPY. */
  benchmark: string;
  /** The session of the shown rebalance's fill, marked as its knowledge time; or null. */
  marker: string | null;
  /** The sessions the time axis labels. */
  ticks: string[];
  /** Whether those labels are years, rather than months. */
  years: boolean;
  /** The drawdown axis's labels, from its floor up to 0 (equity.ts, `drawdownScale`). */
  drawdownTicks: number[];
};

const DASH = "5 4";

/**
 * A run's equity curve and drawdown, after costs (S9.6): the portfolio as a solid line in
 * the strategy's color, the benchmark dashed in gray, so they differ by more than color,
 * and the shown rebalance marked as T. The two charts share their time axis and tooltip.
 * The page gives the same numbers as text and a table, for those who can't see a chart.
 */
export function ResultCharts({
  points,
  benchmark,
  marker,
  ticks,
  years,
  drawdownTicks,
}: ResultChartsProps) {
  const config = {
    value: { label: "Portfolio", color: "var(--chart-1)" },
    benchmark: { label: benchmark, color: "var(--chart-2)" },
    drawdown: { label: "Portfolio", color: "var(--chart-1)" },
    benchmarkDrawdown: { label: benchmark, color: "var(--chart-2)" },
  } satisfies ChartConfig;

  const tick = (session: string) => {
    const date = parseIsoDate(session);
    if (!date) return session;
    return years ? String(date.year) : formatEtMonth(date);
  };
  const label = (session: unknown) => {
    const date = typeof session === "string" ? parseIsoDate(session) : null;
    return date ? `Close, ${formatEtShortDate(date)}` : String(session);
  };
  const axis = {
    dataKey: "session",
    ticks,
    // Drop a label that would crowd its neighbor, as on a phone; keep the first and last.
    interval: "preserveStartEnd" as const,
    minTickGap: 12,
    tickFormatter: tick,
    tickLine: false,
    axisLine: false,
    tickMargin: 6,
  };
  const markerLine = marker ? (
    <ReferenceLine
      x={marker}
      stroke="var(--primary)"
      strokeWidth={1.5}
      strokeDasharray="3 3"
      label={{ value: "T", position: "insideTopLeft", fill: "var(--brand-ink)", fontSize: 11 }}
    />
  ) : null;

  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <LegendItem color="var(--chart-1)" label="Portfolio" />
        <LegendItem color="var(--chart-2)" label={benchmark} dashed={DASH} />
        {marker ? (
          <LegendItem color="var(--primary)" label="T: the rebalance below" dashed="3 3" />
        ) : null}
      </ul>

      <div className="flex flex-col gap-1">
        <h3 className="text-xs font-medium text-muted-foreground">Growth of $1</h3>
        <ChartContainer
          config={config}
          className="aspect-auto h-64 w-full"
          initialDimension={{ width: 640, height: 256 }}
        >
          <LineChart data={points} syncId="run-curve" margin={{ top: 8, right: 12, left: 4 }}>
            <CartesianGrid vertical={false} />
            <XAxis {...axis} />
            <YAxis
              width={64}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value: number) => formatUsd(value)}
            />
            <ReferenceLine y={1} stroke="var(--border)" />
            {markerLine}
            <ChartTooltip
              content={
                <ChartTooltipContent
                  labelFormatter={label}
                  formatter={(value, name, item) => (
                    <TooltipRow
                      color={String(item.color ?? "")}
                      dashed={name === "benchmark"}
                      label={name === "benchmark" ? benchmark : "Portfolio"}
                      value={typeof value === "number" ? formatUsd(value) : "—"}
                    />
                  )}
                />
              }
            />
            <Line
              dataKey="value"
              type="linear"
              stroke="var(--color-value)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              dataKey="benchmark"
              type="linear"
              stroke="var(--color-benchmark)"
              strokeWidth={1.5}
              strokeDasharray={DASH}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ChartContainer>
      </div>

      <div className="flex flex-col gap-1">
        <h3 className="text-xs font-medium text-muted-foreground">Drawdown from the last peak</h3>
        <ChartContainer
          config={config}
          className="aspect-auto h-40 w-full"
          initialDimension={{ width: 640, height: 160 }}
        >
          <ComposedChart data={points} syncId="run-curve" margin={{ top: 8, right: 12, left: 4 }}>
            <CartesianGrid vertical={false} />
            <XAxis {...axis} />
            <YAxis
              width={64}
              tickLine={false}
              axisLine={false}
              domain={[drawdownTicks[0] ?? -0.01, 0]}
              ticks={drawdownTicks}
              tickFormatter={(value: number) => formatPercent(value)}
            />
            {markerLine}
            <ChartTooltip
              content={
                <ChartTooltipContent
                  labelFormatter={label}
                  formatter={(value, name, item) => (
                    <TooltipRow
                      color={String(item.color ?? "")}
                      dashed={name === "benchmarkDrawdown"}
                      label={name === "benchmarkDrawdown" ? benchmark : "Portfolio"}
                      value={typeof value === "number" ? formatPercent(value) : "—"}
                    />
                  )}
                />
              }
            />
            <Area
              dataKey="drawdown"
              type="linear"
              stroke="var(--color-drawdown)"
              fill="var(--color-drawdown)"
              fillOpacity={0.15}
              strokeWidth={1.5}
              isAnimationActive={false}
            />
            <Line
              dataKey="benchmarkDrawdown"
              type="linear"
              stroke="var(--color-benchmarkDrawdown)"
              strokeWidth={1.5}
              strokeDasharray={DASH}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ChartContainer>
      </div>
    </div>
  );
}

function LegendItem({ color, label, dashed }: { color: string; label: string; dashed?: string }) {
  return (
    <li className="flex items-center gap-1.5">
      <svg aria-hidden width="20" height="6" className="shrink-0">
        <line
          x1="0"
          y1="3"
          x2="20"
          y2="3"
          stroke={color}
          strokeWidth="2"
          strokeDasharray={dashed}
        />
      </svg>
      {label}
    </li>
  );
}

function TooltipRow({
  color,
  dashed,
  label,
  value,
}: {
  color: string;
  dashed: boolean;
  label: string;
  value: string;
}) {
  return (
    <div className="flex w-full items-center justify-between gap-4">
      <span className="flex items-center gap-1.5 text-muted-foreground">
        <svg aria-hidden width="14" height="6" className="shrink-0">
          <line
            x1="0"
            y1="3"
            x2="14"
            y2="3"
            stroke={color}
            strokeWidth="2"
            strokeDasharray={dashed ? "4 3" : undefined}
          />
        </svg>
        {label}
      </span>
      <span className="font-mono font-medium text-foreground tabular-nums">{value}</span>
    </div>
  );
}
