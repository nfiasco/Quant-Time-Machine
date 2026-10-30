"use client";

import { useState, type FormEvent } from "react";
import { Icon } from "./icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatEtDate, formatEtMonthYear, formatEtTime, parseAsOf } from "@/lib/time";

const strategies = ["Momentum", "Value", "Quality"] as const;
type Strategy = (typeof strategies)[number];
type Period = 1 | 3 | 5;

// Deterministic synthetic series for the landing-page demo, never market data.
function sampleSeries(strategy: Strategy, period: Period, seed: number) {
  const factor = { Momentum: 1.5, Value: 1.1, Quality: 1.3 }[strategy];
  return Array.from({ length: 49 }, (_, i) => {
    const wave = Math.sin(i * 1.35) * 2.2 + Math.sin(i * 0.49) * 4;
    return (
      100 +
      i * factor * (period / 5) +
      wave * Math.min(i / 4, 1) +
      Math.sin(i * 0.2 + seed) * i * 0.08
    );
  });
}

export function ResearchPreview() {
  const [applied, setApplied] = useState({
    strategy: "Momentum" as Strategy,
    date: "2020-01-01",
  });
  const [period, setPeriod] = useState<Period>(5);
  const [hasRun, setHasRun] = useState(false);
  const moment = parseAsOf(applied.date)!;
  const cutoff = new Date(Date.UTC(moment.year, moment.month - 1, moment.day));
  const seed = cutoff.getTime() / 86_400_000;
  const values = sampleSeries(applied.strategy, period, seed);
  const benchmark = sampleSeries("Value", period, seed + 3).map(
    (value, i) => value - i * 0.3 * (period / 5),
  );
  const ceiling = Math.ceil(Math.max(...values, ...benchmark) / 20) * 20;
  const y = (value: number) => 225 - ((value - 80) / (ceiling - 80)) * 205;
  const points = values
    .map((value, i) => `${50 + i * 13.3},${y(value)}`)
    .join(" ");
  const benchmarkPoints = benchmark
    .map((value, i) => `${50 + i * 13.3},${y(value)}`)
    .join(" ");
  const totalReturn = (values[values.length - 1] / values[0] - 1) * 100;
  const annualReturn =
    ((values[values.length - 1] / values[0]) ** (1 / period) - 1) * 100;
  let peak = values[0];
  let drawdown = 0;
  for (const value of values) {
    peak = Math.max(peak, value);
    drawdown = Math.min(drawdown, (value / peak - 1) * 100);
  }
  const formattedDate = formatEtDate(moment);
  const start = new Date(cutoff);
  start.setUTCFullYear(start.getUTCFullYear() - period);
  const tickLabels = Array.from({ length: 5 }, (_, i) => {
    const tick = new Date(
      start.getTime() + ((cutoff.getTime() - start.getTime()) * i) / 4,
    );
    return formatEtMonthYear({
      year: tick.getUTCFullYear(),
      month: tick.getUTCMonth() + 1,
    });
  });

  function runPreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setApplied({
      strategy: fields.get("strategy") as Strategy,
      date: String(fields.get("as-of-date")),
    });
    setHasRun(true);
  }

  return (
    <div className="research-console">
      <div className="console-topbar">
        <div className="window-dots">
          <i />
          <i />
          <i />
        </div>
        <span>QUANT TIME MACHINE / RESEARCH WORKSPACE</span>
        <span className="sample-badge">
          <i /> Interactive demo
        </span>
      </div>
      <div className="console-body">
        <form className="research-controls" onSubmit={runPreview}>
          <span className="eyebrow">YOUR NEXT HYPOTHESIS</span>
          <h3>
            Every idea starts with a <em>what if.</em>
          </h3>
          <p>
            Step into a historical moment. Explore how a sample strategy could
            look.
          </p>
          <Label htmlFor="strategy">
            01 <span>Choose a strategy</span>
          </Label>
          <div className="select-wrap">
            <select id="strategy" name="strategy" defaultValue="Momentum">
              {strategies.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </div>
          <Label htmlFor="as-of-date">
            02 <span>Set your point in time</span>
          </Label>
          <Input
            id="as-of-date"
            name="as-of-date"
            type="date"
            required
            min="2016-01-01"
            max="2024-12-31"
            defaultValue="2020-01-01"
          />
          <Button className="button button-primary" type="submit">
            Run sample backtest <Icon name="arrow" />
          </Button>
          <span className="control-note">
            <Icon name="check" /> No account needed. Just curiosity.
          </span>
        </form>
        <div className="research-results">
          <div className="results-heading">
            <div>
              <span className="eyebrow">PORTFOLIO PERFORMANCE</span>
              <h3>
                {applied.strategy} <span>/ Sample portfolio</span>
              </h3>
            </div>
            <span className="data-tag">SYNTHETIC DATA</span>
          </div>
          <div className="chart-summary">
            <div>
              <span className="chart-value">
                +{totalReturn.toFixed(2)}
                <small>%</small>
              </span>
              <span className="chart-caption">Cumulative sample return</span>
            </div>
            <div
              className="period-switch"
              role="group"
              aria-label="Backtest duration"
            >
              {([1, 3, 5] as const).map((value) => (
                <Button
                  type="button"
                  key={value}
                  aria-pressed={period === value}
                  onClick={() => setPeriod(value)}
                >
                  {value}Y
                </Button>
              ))}
            </div>
          </div>
          <svg
            className="performance-chart"
            viewBox="0 0 720 270"
            role="img"
            aria-label={`Synthetic ${applied.strategy} portfolio over ${period} ${period === 1 ? "year" : "years"}, returning ${totalReturn.toFixed(2)} percent. Illustrative data only.`}
          >
            <defs>
              <linearGradient id="chart-area" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="0%"
                  stopColor="var(--chart-1)"
                  stopOpacity=".24"
                />
                <stop
                  offset="100%"
                  stopColor="var(--chart-1)"
                  stopOpacity="0"
                />
              </linearGradient>
            </defs>
            {[0, 1, 2, 3, 4].map((i) => {
              const value = 80 + ((ceiling - 80) * i) / 4;
              return (
                <g key={i}>
                  <line
                    x1="50"
                    x2="690"
                    y1={y(value)}
                    y2={y(value)}
                    stroke="var(--foreground)"
                    strokeOpacity=".065"
                  />
                  <text
                    x="0"
                    y={y(value) + 4}
                    fill="var(--muted-foreground)"
                    fontSize="11"
                  >
                    {value.toFixed(0)}
                  </text>
                </g>
              );
            })}
            {[0, 1, 2, 3, 4].map((i) => (
              <line
                key={i}
                x1={50 + i * 159.6}
                x2={50 + i * 159.6}
                y1="20"
                y2="225"
                stroke="var(--foreground)"
                strokeOpacity=".035"
              />
            ))}
            <polygon
              points={`50,225 ${points} 688.4,225`}
              fill="url(#chart-area)"
            />
            <polyline
              points={benchmarkPoints}
              stroke="var(--chart-2)"
              strokeWidth="1.7"
              fill="none"
              strokeDasharray="4 4"
            />
            <polyline
              points={points}
              stroke="var(--chart-1)"
              strokeWidth="2.5"
              strokeLinejoin="round"
              fill="none"
            />
            <circle
              cx="688.4"
              cy={y(values[values.length - 1])}
              r="4"
              fill="var(--chart-1)"
              stroke="var(--card)"
              strokeWidth="5"
            />
            {tickLabels.map((label, i) => (
              <text
                key={i}
                x={50 + i * 159.6}
                y="255"
                textAnchor={i === 0 ? "start" : i === 4 ? "end" : "middle"}
                fill="var(--muted-foreground)"
                fontSize="11"
              >
                {label}
              </text>
            ))}
          </svg>
          <div className="chart-legend">
            <span>
              <i /> Sample strategy
            </span>
            <span>
              <i /> Sample benchmark
            </span>
            <span>Indexed to 100</span>
          </div>
          <div className="result-stats">
            <div>
              <span>Annualized return</span>
              <strong>+{annualReturn.toFixed(2)}%</strong>
            </div>
            <div>
              <span>Max. drawdown</span>
              <strong>{drawdown.toFixed(2)}%</strong>
            </div>
            <div>
              <span>Historical cutoff</span>
              <strong>{formattedDate}</strong>
              <span className="cutoff-time">{formatEtTime(moment)}</span>
            </div>
          </div>
          <p className="demo-disclaimer" role="status">
            {hasRun
              ? `Preview updated: ${applied.strategy}, as of ${formattedDate}. `
              : "Explore the controls to update this preview. "}
            Illustrative data only; this demo does not run the research engine.
          </p>
        </div>
      </div>
    </div>
  );
}
