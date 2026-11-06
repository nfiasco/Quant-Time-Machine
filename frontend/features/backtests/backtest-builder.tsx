"use client";

import { useState } from "react";
import { PlayIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { canonicalPreset } from "@/features/backtests/presets";
import { SpecSummary } from "@/features/backtests/spec-summary";
import type { ExperimentSpec } from "@/features/backtests/types";
import {
  decisionFromTime,
  decisionTime,
  validateSpec,
} 
//from "@/features/backtests/validation";
from "./validation";

// TODO: replace with the shadcn NativeSelect (`npx shadcn@latest add native-select`)
// once it's added to components/ui. These classes match Input.
const selectClassName =
  "h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 md:text-sm dark:bg-input/30";

type BacktestBuilderProps = {
  /** The spec the form starts from, for example a preset's. Defaults to the canonical example. */
  initialSpec?: ExperimentSpec;
};

/** The form that builds an experiment spec (S9.5). Submitting isn't wired up until POST /v1/backtests exists (S8.4). */
export function BacktestBuilder({
  initialSpec = canonicalPreset.spec,
}: BacktestBuilderProps) {
  const [spec, setSpec] = useState<ExperimentSpec>(initialSpec);
  // The cost field's text, so clearing it shows an error instead of silently becoming 0.
  const [costText, setCostText] = useState(String(initialSpec.costs.bps_per_trade));

  const errors = validateSpec(spec);
  const isValid = Object.keys(errors).length === 0;

  function fieldError(path: string) {
    const message = errors[path];
    return message ? <FieldError id={`${path}-error`}>{message}</FieldError> : null;
  }

  function invalidProps(path: string) {
    return errors[path]
      ? { "aria-invalid": true, "aria-describedby": `${path}-error` }
      : {};
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
      <Card>
        <CardHeader>
          <CardTitle>Configuration</CardTitle>
          <CardDescription>
            Every input is point-in-time: each decision sees only what was public by then.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form noValidate onSubmit={(event) => event.preventDefault()}>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="name">Name</FieldLabel>
                <Input
                  id="name"
                  value={spec.name}
                  onChange={(e) => {
                    const name = e.target.value;
                    setSpec((s) => ({ ...s, name }));
                  }}
                  {...invalidProps("name")}
                />
                {fieldError("name")}
              </Field>

              <div className="grid gap-4 md:grid-cols-2">
                <Field>
                  <FieldLabel htmlFor="period-start">Start date</FieldLabel>
                  <Input
                    id="period-start"
                    type="date"
                    className="font-mono tabular-nums"
                    value={spec.period.start}
                    onChange={(e) => {
                      const start = e.target.value;
                      setSpec((s) => ({ ...s, period: { ...s.period, start } }));
                    }}
                    {...invalidProps("period.start")}
                  />
                  {fieldError("period.start")}
                </Field>
                <Field>
                  <FieldLabel htmlFor="period-end">End date</FieldLabel>
                  <Input
                    id="period-end"
                    type="date"
                    className="font-mono tabular-nums"
                    value={spec.period.end}
                    onChange={(e) => {
                      const end = e.target.value;
                      setSpec((s) => ({ ...s, period: { ...s.period, end } }));
                    }}
                    {...invalidProps("period.end")}
                  />
                  {fieldError("period.end")}
                </Field>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <Field>
                  <FieldLabel htmlFor="rebalance">Rebalance</FieldLabel>
                  <select
                    id="rebalance"
                    className={selectClassName}
                    value={spec.schedule.rebalance}
                    disabled
                    aria-describedby="rebalance-description"
                  >
                    <option value="monthly">Monthly</option>
                  </select>
                  <FieldDescription id="rebalance-description">
                    Monthly is the only option in spec v1.
                  </FieldDescription>
                </Field>
                <Field>
                  <FieldLabel htmlFor="decision-time">Decision time (ET)</FieldLabel>
                  <Input
                    id="decision-time"
                    type="time"
                    className="font-mono tabular-nums"
                    value={decisionTime(spec.schedule.decision) ?? ""}
                    onChange={(e) => {
                      const decision = decisionFromTime(e.target.value);
                      setSpec((s) => ({ ...s, schedule: { ...s.schedule, decision } }));
                    }}
                    {...invalidProps("schedule.decision")}
                  />
                  {errors["schedule.decision"] ? (
                    fieldError("schedule.decision")
                  ) : (
                    <FieldDescription>On the first trading day of each month.</FieldDescription>
                  )}
                </Field>
                <Field>
                  <FieldLabel htmlFor="fill">Fill</FieldLabel>
                  <select
                    id="fill"
                    className={selectClassName}
                    value={spec.schedule.fill}
                    onChange={(e) => {
                      const fill = e.target.value as ExperimentSpec["schedule"]["fill"];
                      setSpec((s) => ({ ...s, schedule: { ...s.schedule, fill } }));
                    }}
                  >
                    <option value="same_day_close">Same-day close</option>
                    <option value="next_day_open">Next-day open</option>
                  </select>
                </Field>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <Field>
                  <FieldLabel htmlFor="weighting">Weighting</FieldLabel>
                  <select
                    id="weighting"
                    className={selectClassName}
                    value={spec.portfolio.weighting}
                    onChange={(e) => {
                      const weighting = e.target.value as ExperimentSpec["portfolio"]["weighting"];
                      setSpec((s) => ({ ...s, portfolio: { ...s.portfolio, weighting } }));
                    }}
                  >
                    <option value="equal">Equal weight</option>
                    <option value="value">Value weight (market cap)</option>
                  </select>
                </Field>
                <Field>
                  <FieldLabel htmlFor="benchmark">Benchmark</FieldLabel>
                  <Input
                    id="benchmark"
                    className="font-mono uppercase"
                    autoCapitalize="characters"
                    spellCheck={false}
                    value={spec.benchmark}
                    onChange={(e) => {
                      const benchmark = e.target.value.toUpperCase().trim();
                      setSpec((s) => ({ ...s, benchmark }));
                    }}
                    {...invalidProps("benchmark")}
                  />
                  {fieldError("benchmark")}
                </Field>
                <Field>
                  <FieldLabel htmlFor="costs">Costs (bps per trade)</FieldLabel>
                  <Input
                    id="costs"
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step="any"
                    className="font-mono tabular-nums"
                    value={costText}
                    onChange={(e) => {
                      const text = e.target.value;
                      setCostText(text);
                      const bps = text.trim() === "" ? Number.NaN : Number(text);
                      setSpec((s) => ({ ...s, costs: { bps_per_trade: bps } }));
                    }}
                    {...invalidProps("costs.bps_per_trade")}
                  />
                  {fieldError("costs.bps_per_trade")}
                </Field>
              </div>
            </FieldGroup>
          </form>
        </CardContent>
        <CardFooter className="flex-col items-stretch gap-2">
          <Button type="button" disabled>
            <PlayIcon data-icon="inline-start" />
            Run backtest
          </Button>
          <p role="status" className="text-xs text-muted-foreground">
            {isValid
              ? "The spec is valid. Running starts once the backtest API is live (S8.4)."
              : "Fix the highlighted fields to get a valid spec."}
          </p>
        </CardFooter>
      </Card>

      <Card size="sm" className="self-start">
        <CardHeader>
          <CardTitle>Spec preview</CardTitle>
          <CardDescription>
            Universe, signals, and filters come from the preset for now.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <SpecSummary spec={spec} />
        </CardContent>
      </Card>
    </div>
  );
}
