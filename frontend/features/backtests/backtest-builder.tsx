"use client";

import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { CircleAlertIcon, PlayIcon, RotateCcwIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { FieldGroup, FieldLegend, FieldSeparator, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Spinner } from "@/components/ui/spinner";
import { startBacktest } from "@/features/backtests/actions";
import { describeFailure } from "@/features/backtests/api-failure";
import { BuilderField, SectionError } from "@/features/backtests/builder-field";
import {
  canonicalJson,
  draftFromSpec,
  specFromDraft,
  type BuilderDraft,
} from "@/features/backtests/draft";
import {
  errorSlots,
  placeErrors,
  withoutSections,
  type EditDraft,
} from "@/features/backtests/field-errors";
import { FilterFields } from "@/features/backtests/filter-fields";
import { PortfolioFields } from "@/features/backtests/portfolio-fields";
import { canonicalPreset } from "@/features/backtests/presets";
import { SignalFields } from "@/features/backtests/signal-fields";
import type { SeriesChoice, SignalKinds } from "@/features/backtests/signal-kinds";
import { SpecSummary } from "@/features/backtests/spec-summary";
import type { ExperimentSpec } from "@/features/backtests/types";
import { UNIVERSES } from "@/features/backtests/universes";
import { validateDraft, type SpecErrors } from "@/features/backtests/validation";
import type { ApiFailure } from "@/lib/api/errors";

const FORM_ID = "bt-form";

type BacktestBuilderProps = {
  /** The spec the form starts from: a preset's, or an earlier run's. */
  initialSpec?: ExperimentSpec;
  /** The kinds of signal from the signal catalog, whose schemas build the signals' fields. */
  kinds: SignalKinds;
  /** The series a macro_change can follow, from the series catalog. */
  series: SeriesChoice[];
};

/** Why the last submit didn't start a run, when it wasn't a field's problem. */
type Problem = { title: string; messages: string[] };

/**
 * The form that builds an experiment spec and runs it (S9.5). It checks what it can as you
 * type (validation.ts); running sends the spec to the API through a Server Action, which
 * opens the run's page. The API's 422 errors land beside the fields their paths name, and
 * stay until a field in their section changes.
 */
export function BacktestBuilder({
  initialSpec = canonicalPreset.spec,
  kinds,
  series,
}: BacktestBuilderProps) {
  const [draft, setDraft] = useState<BuilderDraft>(() => draftFromSpec(initialSpec, kinds.kinds));
  const [serverErrors, setServerErrors] = useState<SpecErrors>({});
  const [problem, setProblem] = useState<Problem | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [focusRequest, setFocusRequest] = useState(0);
  const [isPending, startTransition] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);

  const spec = specFromDraft(draft, kinds.kinds);
  const clientErrors = validateDraft(draft, kinds.kinds);
  // The form's own check wins where both have something to say: it's about what's there now.
  const errors: SpecErrors = { ...serverErrors, ...clientErrors };
  const clientCount = Object.keys(clientErrors).length;
  const serverCount = Object.keys(serverErrors).length;

  // A run's spec lists its signals in another order, and is still the example.
  const exampleJson = useMemo(
    () =>
      canonicalJson(specFromDraft(draftFromSpec(canonicalPreset.spec, kinds.kinds), kinds.kinds)),
    [kinds],
  );
  const isExample = canonicalJson(spec) === exampleJson;

  // After a submit that found problems, move focus to the first field with one, or into the
  // first section with one.
  useEffect(() => {
    if (focusRequest === 0) return;
    const form = formRef.current;
    const target =
      form?.querySelector<HTMLElement>('[aria-invalid="true"]') ??
      form?.querySelector<HTMLElement>(
        "[data-invalid-section] :is(input, select, button):not(:disabled)",
      );
    target?.focus();
  }, [focusRequest]);

  const edit: EditDraft = (sections, change) => {
    setDraft(change);
    setServerErrors((current) => withoutSections(current, sections));
  };

  function reset() {
    setDraft(draftFromSpec(canonicalPreset.spec, kinds.kinds));
    setServerErrors({});
    setProblem(null);
    setAttempted(false);
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isPending) return;
    setAttempted(true);
    setProblem(null);
    if (clientCount > 0) {
      setFocusRequest((count) => count + 1);
      return;
    }

    const submitted = spec;
    const slots = errorSlots(draft, kinds.kinds);
    startTransition(async () => {
      let failure: ApiFailure | undefined;
      try {
        failure = await startBacktest(submitted);
      } catch {
        setProblem({
          title: "Couldn't submit the run",
          messages: ["Something went wrong between this page and the server. Try again."],
        });
        return;
      }
      // Nothing came back: the action opened the run's page.
      if (!failure) return;

      if (failure.kind === "response" && failure.status === 422 && failure.details.length > 0) {
        const placed = placeErrors(failure.details, slots);
        setServerErrors(placed.fields);
        if (placed.other.length > 0) {
          setProblem({ title: "The API can't run this spec", messages: placed.other });
        }
        setFocusRequest((count) => count + 1);
        return;
      }
      const { title, description } = describeFailure(failure);
      setProblem({ title, messages: [description] });
    });
  }

  const universe = UNIVERSES.find((option) => option.id === draft.universe);
  const status = isPending
    ? "Submitting the spec…"
    : clientCount > 0
      ? attempted
        ? "Fix the highlighted fields, then run it."
        : "Fix the highlighted fields to get a valid spec."
      : serverCount > 0
        ? "The API found problems with the spec: see the highlighted fields."
        : problem
          ? "The run didn't start: see the message above."
          : "Ready to run. A spec that already ran on the newest data opens at once.";

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Configuration</h2>
          </CardTitle>
          <CardDescription>
            Every input is point-in-time: each decision sees only what was public by then.
          </CardDescription>
          <CardAction>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isExample || isPending}
              onClick={reset}
            >
              <RotateCcwIcon data-icon="inline-start" />
              {/* Only the icon while the header is narrow: the name stays for screen readers. */}
              <span className="sr-only @md/card-header:not-sr-only">Reset to the example</span>
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          <form
            id={FORM_ID}
            ref={formRef}
            noValidate
            onSubmit={handleSubmit}
            data-pending={isPending ? "" : undefined}
          >
            <FieldGroup>
              <BuilderField id="bt-name" label="Name" error={errors.name}>
                {(control) => (
                  <Input
                    {...control}
                    value={draft.name}
                    onChange={(event) => {
                      const name = event.target.value;
                      edit(["name"], (current) => ({ ...current, name }));
                    }}
                  />
                )}
              </BuilderField>

              <FieldSeparator />
              <FieldSet
                aria-describedby={errors.period ? "bt-period-error" : undefined}
                data-invalid-section={errors.period ? "" : undefined}
              >
                <FieldLegend>Universe and period</FieldLegend>
                <BuilderField
                  id="bt-universe"
                  label="Universe"
                  error={errors["universe.id"]}
                  description={universe?.description}
                >
                  {(control) => (
                    <NativeSelect
                      {...control}
                      className="w-full"
                      value={draft.universe}
                      // One universe exists, so there's nothing to choose yet.
                      disabled={UNIVERSES.length === 1 && Boolean(universe)}
                      onChange={(event) => {
                        const id = event.target.value;
                        edit(["universe"], (current) => ({ ...current, universe: id }));
                      }}
                    >
                      {UNIVERSES.map((option) => (
                        <NativeSelectOption key={option.id} value={option.id}>
                          {option.label}
                        </NativeSelectOption>
                      ))}
                      {universe ? null : (
                        <NativeSelectOption value={draft.universe}>
                          {draft.universe}
                        </NativeSelectOption>
                      )}
                    </NativeSelect>
                  )}
                </BuilderField>
                <div className="grid gap-4 @md/field-group:grid-cols-2">
                  <BuilderField id="bt-start" label="Start date" error={errors["period.start"]}>
                    {(control) => (
                      <Input
                        {...control}
                        type="date"
                        className="font-mono tabular-nums"
                        value={draft.start}
                        onChange={(event) => {
                          const start = event.target.value;
                          edit(["period"], (current) => ({ ...current, start }));
                        }}
                      />
                    )}
                  </BuilderField>
                  <BuilderField id="bt-end" label="End date" error={errors["period.end"]}>
                    {(control) => (
                      <Input
                        {...control}
                        type="date"
                        className="font-mono tabular-nums"
                        value={draft.end}
                        onChange={(event) => {
                          const end = event.target.value;
                          edit(["period"], (current) => ({ ...current, end }));
                        }}
                      />
                    )}
                  </BuilderField>
                </div>
                <SectionError id="bt-period-error" error={errors.period} />
              </FieldSet>

              <FieldSeparator />
              <FieldSet
                aria-describedby={errors.schedule ? "bt-schedule-error" : undefined}
                data-invalid-section={errors.schedule ? "" : undefined}
              >
                <FieldLegend>Schedule</FieldLegend>
                <div className="grid gap-4 @lg/field-group:grid-cols-3">
                  <BuilderField
                    id="bt-rebalance"
                    label="Rebalance"
                    description="Monthly is the only option in spec v1."
                  >
                    {(control) => (
                      <NativeSelect {...control} className="w-full" value="monthly" disabled>
                        <NativeSelectOption value="monthly">Monthly</NativeSelectOption>
                      </NativeSelect>
                    )}
                  </BuilderField>
                  <BuilderField
                    id="bt-decision-time"
                    label="Decision time (ET)"
                    error={errors["schedule.decision"]}
                    description="On the first trading day of each month."
                  >
                    {(control) => (
                      <Input
                        {...control}
                        type="time"
                        className="font-mono tabular-nums"
                        value={draft.decisionTime}
                        onChange={(event) => {
                          const decisionTime = event.target.value;
                          edit(["schedule"], (current) => ({ ...current, decisionTime }));
                        }}
                      />
                    )}
                  </BuilderField>
                  <BuilderField
                    id="bt-fill"
                    label="Fill"
                    error={errors["schedule.fill"]}
                    description="When the decision's trades fill, always after it."
                  >
                    {(control) => (
                      <NativeSelect
                        {...control}
                        className="w-full"
                        value={draft.fill}
                        onChange={(event) => {
                          const fill = event.target.value as BuilderDraft["fill"];
                          edit(["schedule"], (current) => ({ ...current, fill }));
                        }}
                      >
                        <NativeSelectOption value="same_day_close">
                          Same-day close
                        </NativeSelectOption>
                        <NativeSelectOption value="next_day_open">Next-day open</NativeSelectOption>
                      </NativeSelect>
                    )}
                  </BuilderField>
                </div>
                <SectionError id="bt-schedule-error" error={errors.schedule} />
              </FieldSet>

              <FieldSeparator />
              <SignalFields
                draft={draft}
                kinds={kinds}
                series={series}
                errors={errors}
                onEdit={edit}
              />

              <FieldSeparator />
              <FilterFields draft={draft} errors={errors} onEdit={edit} />

              <FieldSeparator />
              <PortfolioFields draft={draft} errors={errors} onEdit={edit} />

              <FieldSeparator />
              <FieldSet>
                <FieldLegend>Benchmark and costs</FieldLegend>
                <div className="grid gap-4 @lg/field-group:grid-cols-3">
                  <BuilderField
                    id="bt-benchmark"
                    label="Benchmark"
                    error={errors.benchmark}
                    description="The ticker the results are compared with."
                  >
                    {(control) => (
                      <Input
                        {...control}
                        className="font-mono uppercase"
                        autoCapitalize="characters"
                        autoComplete="off"
                        spellCheck={false}
                        value={draft.benchmark}
                        onChange={(event) => {
                          const benchmark = event.target.value.toUpperCase().trim();
                          edit(["benchmark"], (current) => ({ ...current, benchmark }));
                        }}
                      />
                    )}
                  </BuilderField>
                  <BuilderField
                    id="bt-costs"
                    label="Costs (bps per trade)"
                    error={errors["costs.bps_per_trade"]}
                    description="Charged on the value of every trade: 10 is 0.1%."
                  >
                    {(control) => (
                      <Input
                        {...control}
                        type="number"
                        inputMode="decimal"
                        min={0}
                        step="any"
                        className="font-mono tabular-nums"
                        value={draft.costs}
                        onChange={(event) => {
                          const costs = event.target.value;
                          edit(["costs"], (current) => ({ ...current, costs }));
                        }}
                      />
                    )}
                  </BuilderField>
                  <BuilderField
                    id="bt-delisting"
                    label="Delisting loss (%)"
                    error={errors["delisting.assumed_return"]}
                    description="If a holding stops trading: 0 keeps its last close, 100 writes it off."
                  >
                    {(control) => (
                      <Input
                        {...control}
                        type="number"
                        inputMode="decimal"
                        min={0}
                        max={100}
                        step="any"
                        className="font-mono tabular-nums"
                        value={draft.delistingLoss}
                        onChange={(event) => {
                          const delistingLoss = event.target.value;
                          edit(["delisting"], (current) => ({ ...current, delistingLoss }));
                        }}
                      />
                    )}
                  </BuilderField>
                </div>
              </FieldSet>
            </FieldGroup>
          </form>
        </CardContent>
        <CardFooter className="flex-col items-stretch gap-3">
          {problem ? (
            <Alert variant="destructive">
              <CircleAlertIcon />
              <AlertTitle>{problem.title}</AlertTitle>
              <AlertDescription>
                {problem.messages.length === 1 ? (
                  <p>{problem.messages[0]}</p>
                ) : (
                  <ul className="list-disc pl-4">
                    {problem.messages.map((message) => (
                      <li key={message}>{message}</li>
                    ))}
                  </ul>
                )}
              </AlertDescription>
            </Alert>
          ) : null}
          {/* aria-disabled rather than disabled, so focus stays on it while the run is sent:
              handleSubmit ignores a second submit. */}
          <Button
            type="submit"
            form={FORM_ID}
            aria-disabled={isPending || undefined}
            className="aria-disabled:opacity-50"
          >
            {isPending ? (
              <Spinner aria-hidden data-icon="inline-start" />
            ) : (
              <PlayIcon data-icon="inline-start" />
            )}
            Run backtest
          </Button>
          <p role="status" className="text-xs text-pretty text-muted-foreground">
            {status}
          </p>
        </CardFooter>
      </Card>

      <Card
        size="sm"
        className="self-start xl:sticky xl:top-20 xl:max-h-[calc(100svh-6rem)] xl:overflow-y-auto"
      >
        <CardHeader>
          <CardTitle>
            <h2>Spec preview</h2>
          </CardTitle>
          <CardDescription>
            The form in plain language, and the JSON the run is given.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <SpecSummary spec={spec} />
        </CardContent>
      </Card>
    </div>
  );
}
