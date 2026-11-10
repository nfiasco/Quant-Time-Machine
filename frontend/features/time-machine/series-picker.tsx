"use client";

import { Checkbox } from "@/components/ui/checkbox";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { MAX_ENTRIES } from "@/features/time-machine/params";
import type { SeriesOption, SeriesOptions } from "@/features/time-machine/picker-options";

type SeriesPickerProps = {
  /** The fieldset's id, so the form can move focus to it. */
  id: string;
  value: string[];
  onChange: (series: string[]) => void;
  series: SeriesOptions;
  error?: string;
  errorId: string;
};

/** Checkboxes for the catalog's economic series, plus any chosen ID it doesn't list. */
export function SeriesPicker({ id, value, onChange, series, error, errorId }: SeriesPickerProps) {
  const listed = new Set(series.options.map((option) => option.id));
  const unlisted: SeriesOption[] = value
    .filter((seriesId) => !listed.has(seriesId))
    .map((seriesId) => ({
      id: seriesId,
      title: series.loaded ? "Not in our catalog" : "Couldn't check this ID",
      detail: "",
    }));
  const atMax = value.length >= MAX_ENTRIES;

  function toggle(seriesId: string, checked: boolean) {
    if (!checked) onChange(value.filter((item) => item !== seriesId));
    else if (!value.includes(seriesId) && !atMax) onChange([...value, seriesId]);
  }

  return (
    <FieldSet id={id} aria-describedby={error ? errorId : undefined}>
      <FieldLegend variant="label">Economic series</FieldLegend>
      <FieldDescription className="text-xs">
        Each value counts from its release time. A revision is a later vintage, so it
        shows as not yet known.
      </FieldDescription>
      <FieldGroup data-slot="checkbox-group" className="gap-3">
        {[...series.options, ...unlisted].map((option) => {
          const checked = value.includes(option.id);
          const inputId = `${id}-${option.id}`;
          return (
            <Field key={option.id} orientation="horizontal">
              <Checkbox
                id={inputId}
                checked={checked}
                disabled={!checked && atMax}
                onCheckedChange={(state) => toggle(option.id, state === true)}
              />
              <FieldContent>
                <FieldLabel htmlFor={inputId} className="flex-wrap gap-x-2 gap-y-0 font-normal">
                  <span className="font-mono text-xs font-medium">{option.id}</span>
                  <span>{option.title}</span>
                </FieldLabel>
                {option.detail ? (
                  <FieldDescription className="text-xs">{option.detail}</FieldDescription>
                ) : null}
              </FieldContent>
            </Field>
          );
        })}
      </FieldGroup>
      {!series.loaded ? (
        <p className="text-xs text-muted-foreground">
          Couldn&apos;t load the series list. Try again in a moment.
        </p>
      ) : null}
      {error ? <FieldError id={errorId}>{error}</FieldError> : null}
    </FieldSet>
  );
}
