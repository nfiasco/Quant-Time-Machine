"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { HistoryIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import {
  catalogAsOf,
  explorerHref,
  validateValues,
  valuesKey,
  valuesOf,
  type ExplorerValues,
  type FieldErrors,
  type ParamName,
} from "@/features/time-machine/params";
import type { CompanyOptions, SeriesOptions } from "@/features/time-machine/picker-options";
import { SeriesPicker } from "@/features/time-machine/series-picker";
import { TickerPicker } from "@/features/time-machine/ticker-picker";
import { formatEtDateTime, parseIsoDate } from "@/lib/time";

const PARAMS: readonly ParamName[] = ["as_of", "tickers", "series"];
const ERROR_ID: Record<ParamName, string> = {
  as_of: "as_of-error",
  tickers: "tickers-error",
  series: "series-error",
};

type ExplorerFormProps = {
  /** `valuesKey` of the URL's values. When it changes on back or forward, the form resets. */
  urlKey: string;
  /** What the URL holds. */
  initialValues: ExplorerValues;
  /** Problems with the URL, and the API's errors for its fields. */
  serverErrors: FieldErrors;
  companies: CompanyOptions;
  series: SeriesOptions;
  /** What the status line says while nothing loads, such as "Showing what was known at …". */
  status: string;
};

/**
 * The Time Machine's controls. Submitting writes the choices into the URL, which the
 * page reads, so the URL always holds the view. While the next snapshot loads, the form
 * carries `data-pending`, which dims the results (GUIDELINES.md §6).
 */
export function ExplorerForm({
  urlKey,
  initialValues,
  serverErrors,
  companies,
  series,
  status,
}: ExplorerFormProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [values, setValues] = useState(initialValues);
  const [clientErrors, setClientErrors] = useState<FieldErrors>({});
  // Fields edited since the page loaded: their server errors no longer apply.
  const [edited, setEdited] = useState<readonly ParamName[]>([]);
  const [syncedKey, setSyncedKey] = useState(urlKey);
  const [expectedKey, setExpectedKey] = useState<string | null>(null);
  const [pendingLabel, setPendingLabel] = useState("");

  // The URL changed. After this form's own submit, keep what's in the form (edits made
  // while it loaded included); after back or forward, show what the URL now holds.
  if (urlKey !== syncedKey) {
    setSyncedKey(urlKey);
    setExpectedKey(null);
    setEdited([]);
    if (urlKey !== expectedKey) {
      setValues(initialValues);
      setClientErrors({});
    }
  }

  const errors: FieldErrors = {};
  for (const name of PARAMS) {
    const message = clientErrors[name] ?? (edited.includes(name) ? undefined : serverErrors[name]);
    if (message) errors[name] = message;
  }

  // The ticker search lists the universe on the date being picked.
  const draftDate = values.date ? parseIsoDate(values.date) : null;

  function update(name: ParamName, patch: Partial<ExplorerValues>) {
    setValues((current) => ({ ...current, ...patch }));
    setClientErrors((current) => {
      if (!(name in current)) return current;
      const next = { ...current };
      delete next[name];
      return next;
    });
    setEdited((current) => (current.includes(name) ? current : [...current, name]));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const { errors: found, query } = validateValues(values);
    setClientErrors(found);
    if (!query) {
      focusFirstInvalid(found);
      return;
    }

    const key = valuesKey(valuesOf(query));
    setEdited([]);
    setPendingLabel(formatEtDateTime(query.moment));
    if (key === urlKey) {
      // Same view: ask the server again rather than pushing a duplicate history entry.
      startTransition(() => router.refresh());
      return;
    }
    setExpectedKey(key);
    startTransition(() => router.push(explorerHref(query), { scroll: false }));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Look back from a moment</h2>
        </CardTitle>
        <CardDescription className="text-pretty">
          Choose a knowledge time, then companies or economic series. The address updates,
          so the link always reproduces what you see.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          noValidate
          onSubmit={handleSubmit}
          data-pending={isPending ? "" : undefined}
          className="flex flex-col gap-6"
        >
          <div className="grid gap-6 lg:grid-cols-2">
            <FieldGroup>
              <FieldSet aria-describedby={errors.as_of ? ERROR_ID.as_of : undefined}>
                <FieldLegend variant="label">Knowledge time (ET)</FieldLegend>
                <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,9rem)] gap-2">
                  <Field data-invalid={errors.as_of ? true : undefined}>
                    <FieldLabel htmlFor="tm-date" className="text-xs font-normal">
                      Date
                    </FieldLabel>
                    <Input
                      id="tm-date"
                      type="date"
                      value={values.date}
                      onChange={(event) => update("as_of", { date: event.target.value })}
                      aria-invalid={errors.as_of ? true : undefined}
                      aria-describedby={errors.as_of ? ERROR_ID.as_of : "tm-time-help"}
                      className="font-mono tabular-nums"
                    />
                  </Field>
                  <Field data-invalid={errors.as_of ? true : undefined}>
                    <FieldLabel htmlFor="tm-time" className="text-xs font-normal">
                      Time
                    </FieldLabel>
                    <Input
                      id="tm-time"
                      type="time"
                      step={60}
                      value={values.time}
                      onChange={(event) => update("as_of", { time: event.target.value })}
                      aria-invalid={errors.as_of ? true : undefined}
                      aria-describedby={errors.as_of ? ERROR_ID.as_of : "tm-time-help"}
                      className="font-mono tabular-nums"
                    />
                  </Field>
                </div>
                <FieldDescription id="tm-time-help" className="text-xs">
                  New York time. A blank time means 09:30 ET, the market open.
                </FieldDescription>
                {errors.as_of ? (
                  <FieldError id={ERROR_ID.as_of}>{errors.as_of}</FieldError>
                ) : null}
              </FieldSet>

              <Field data-invalid={errors.tickers ? true : undefined}>
                <FieldLabel htmlFor="tm-tickers">Companies</FieldLabel>
                <TickerPicker
                  id="tm-tickers"
                  value={values.tickers}
                  onChange={(tickers) => update("tickers", { tickers })}
                  draftAsOf={draftDate ? catalogAsOf(draftDate) : null}
                  initialCompanies={companies}
                  invalid={Boolean(errors.tickers)}
                  describedBy={errors.tickers ? ERROR_ID.tickers : "tm-tickers-help"}
                />
                <FieldDescription id="tm-tickers-help" className="text-xs">
                  Up to 10. A ticker means the company that used it at the knowledge time,
                  so FB is Facebook in 2020.
                </FieldDescription>
                {errors.tickers ? (
                  <FieldError id={ERROR_ID.tickers}>{errors.tickers}</FieldError>
                ) : null}
              </Field>
            </FieldGroup>

            <SeriesPicker
              id="tm-series"
              value={values.series}
              onChange={(chosen) => update("series", { series: chosen })}
              series={series}
              error={errors.series}
              errorId={ERROR_ID.series}
            />
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
            <Button type="submit" className="sm:self-start">
              {isPending ? (
                <Spinner aria-hidden data-icon="inline-start" />
              ) : (
                <HistoryIcon data-icon="inline-start" />
              )}
              Show what was known
            </Button>
            <p role="status" className="text-xs text-pretty text-muted-foreground">
              {isPending ? `Loading what was known at ${pendingLabel}…` : status}
            </p>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

/** Moves focus to the first field with an error, in the order they appear. */
function focusFirstInvalid(errors: FieldErrors) {
  const target = errors.as_of
    ? document.getElementById("tm-date")
    : errors.tickers
      ? document.getElementById("tm-tickers")
      : errors.series
        ? document.querySelector<HTMLElement>("#tm-series [role='checkbox']:not([disabled])")
        : null;
  target?.focus();
}
