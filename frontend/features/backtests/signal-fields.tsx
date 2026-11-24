"use client";

import { PlusIcon, Trash2Icon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { FieldDescription, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { BuilderField, SectionError, type ControlProps } from "@/features/backtests/builder-field";
import { describeSignal } from "@/features/backtests/describe-signal";
import {
  addSignal,
  changeSignalKind,
  removeSignal,
  setSignalId,
  setSignalParam,
  type BuilderDraft,
  type ParamChoices,
  type SignalRow,
} from "@/features/backtests/draft";
import type { EditDraft, Section } from "@/features/backtests/field-errors";
import {
  findKind,
  type ParamField,
  type SeriesChoice,
  type SignalKinds,
} from "@/features/backtests/signal-kinds";
import type { SpecErrors } from "@/features/backtests/validation";

// A signal's ID and kind decide what the filters and the ranking point at, so editing one
// can fix or break their errors too.
const SECTIONS: readonly Section[] = ["signals", "filters", "portfolio"];
const ADD_ID = "bt-add-signal";

type SignalFieldsProps = {
  draft: BuilderDraft;
  kinds: SignalKinds;
  /** The series a macro_change can follow, or none if the series catalog didn't load. */
  series: SeriesChoice[];
  errors: SpecErrors;
  onEdit: EditDraft;
};

/**
 * The spec's signals: each one's ID, kind, and parameters, with fields built from the
 * kind's schema in the signal catalog (S8.5). Without the catalog, the signals are shown
 * but can't be changed.
 */
export function SignalFields({ draft, kinds, series, errors, onEdit }: SignalFieldsProps) {
  const choices: ParamChoices = { series: series.map((choice) => choice.id) };
  const first = kinds.kinds[0];
  const sectionError = errors.signals;

  return (
    <FieldSet
      aria-describedby={sectionError ? "bt-signals-error" : "bt-signals-description"}
      data-invalid-section={sectionError ? "" : undefined}
    >
      <FieldLegend>Signals</FieldLegend>
      <FieldDescription id="bt-signals-description">
        What the filters and the ranking test, each under an ID of its own. Each decision computes
        them from what was public by then.
      </FieldDescription>

      {draft.signals.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {draft.signals.map((row, index) => (
            <li key={row.key}>
              {kinds.loaded ? (
                <SignalRowFields
                  row={row}
                  index={index}
                  kinds={kinds}
                  series={series}
                  choices={choices}
                  errors={errors}
                  onEdit={onEdit}
                />
              ) : (
                <ReadOnlySignal row={row} />
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">
          No signals. Without filters or a ranking, every member of the universe is held.
        </p>
      )}
      <SectionError id="bt-signals-error" error={sectionError} />

      {kinds.loaded && first ? (
        <Button
          id={ADD_ID}
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() => onEdit(SECTIONS, (current) => addSignal(current, first, choices))}
        >
          <PlusIcon data-icon="inline-start" />
          Add a signal
        </Button>
      ) : null}
    </FieldSet>
  );
}

type SignalRowFieldsProps = {
  row: SignalRow;
  /** Its place in the list, which screen readers hear with each label. */
  index: number;
  kinds: SignalKinds;
  series: SeriesChoice[];
  choices: ParamChoices;
  errors: SpecErrors;
  onEdit: EditDraft;
};

function SignalRowFields({
  row,
  index,
  kinds,
  series,
  choices,
  errors,
  onEdit,
}: SignalRowFieldsProps) {
  const kind = findKind(kinds.kinds, row.type);
  const context = `of signal ${index + 1}`;
  const path = `signals.${row.id}`;
  const prefix = `bt-signal-${row.key}`;
  const params = (kind?.fields ?? []).filter((field) => field.kind !== "fixed");

  return (
    <div className="relative flex flex-col gap-3 rounded-lg border p-3">
      <div className="grid gap-3 @md/field-group:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] @md/field-group:items-start">
        <BuilderField
          id={`${prefix}-id`}
          label="ID"
          labelContext={context}
          error={errors[path]}
          compact
        >
          {(control) => (
            <Input
              {...control}
              className="font-mono"
              value={row.id}
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              onChange={(event) => {
                // IDs are lowercase with underscores, so typing "Mom 6" gives "mom_6".
                const id = event.target.value.toLowerCase().replace(/\s/g, "_");
                onEdit(SECTIONS, (current) => setSignalId(current, row.key, id));
              }}
            />
          )}
        </BuilderField>
        <BuilderField
          id={`${prefix}-type`}
          label="Kind"
          labelContext={context}
          error={errors[`${path}.type`]}
          compact
        >
          {(control) => (
            <NativeSelect
              {...control}
              className="w-full"
              value={row.type}
              onChange={(event) => {
                const next = findKind(kinds.kinds, event.target.value);
                if (next)
                  onEdit(SECTIONS, (current) => changeSignalKind(current, row.key, next, choices));
              }}
            >
              {kinds.kinds.map((option) => (
                <NativeSelectOption key={option.type} value={option.type}>
                  {option.label}
                </NativeSelectOption>
              ))}
              {kind ? null : <NativeSelectOption value={row.type}>{row.type}</NativeSelectOption>}
            </NativeSelect>
          )}
        </BuilderField>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          // In the row's corner while the fields stack; in its own column beside them after.
          className="absolute top-2 right-2 @md/field-group:static @md/field-group:mt-6"
          aria-label={row.id ? `Remove the signal ${row.id}` : "Remove this signal"}
          onClick={() => {
            onEdit(SECTIONS, (current) => removeSignal(current, row.key));
            requestAnimationFrame(() => document.getElementById(ADD_ID)?.focus());
          }}
        >
          <Trash2Icon />
        </Button>
      </div>

      {kind ? (
        <p className="text-xs text-pretty text-muted-foreground">{withCode(kind.description)}</p>
      ) : null}

      {params.length > 0 ? (
        <div className="grid gap-3 @md/field-group:grid-cols-2 @3xl/field-group:grid-cols-3">
          {params.map((field) => (
            <BuilderField
              key={field.name}
              id={`${prefix}-${field.name}`}
              label={field.label}
              labelContext={context}
              error={errors[`${path}.${field.name}`]}
              description={field.description ? withCode(field.description) : undefined}
              compact
            >
              {(control) => (
                <ParamControl
                  control={control}
                  field={field}
                  value={row.params[field.name] ?? ""}
                  series={field.name === "series" ? series : []}
                  onChange={(value) =>
                    onEdit(SECTIONS, (current) =>
                      setSignalParam(current, row.key, kind, field.name, value),
                    )
                  }
                />
              )}
            </BuilderField>
          ))}
        </div>
      ) : null}
    </div>
  );
}

type ParamControlProps = {
  control: ControlProps;
  field: ParamField;
  value: string;
  /** For a `series` parameter: the series catalog's choices. */
  series: SeriesChoice[];
  onChange: (value: string) => void;
};

/** The control for one parameter, by the kind of value its schema allows. */
function ParamControl({ control, field, value, series, onChange }: ParamControlProps) {
  switch (field.kind) {
    case "integer":
    case "number": {
      const integer = field.kind === "integer";
      // A phone's number pad has no minus key, so offer it only when no value is negative.
      const nonNegative = field.min !== null && field.min >= 0;
      return (
        <Input
          {...control}
          type="number"
          inputMode={nonNegative ? (integer ? "numeric" : "decimal") : undefined}
          step={integer ? 1 : "any"}
          min={field.min ?? undefined}
          max={field.max ?? undefined}
          placeholder={field.default !== null ? String(field.default) : undefined}
          className="font-mono tabular-nums"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      );
    }
    case "choice":
      return (
        <NativeSelect
          {...control}
          className="w-full"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          {field.options.includes(value) && field.required ? null : (
            <NativeSelectOption value="">
              {field.required ? "Choose one" : "Default"}
            </NativeSelectOption>
          )}
          {field.options.map((option) => (
            <NativeSelectOption key={option} value={option}>
              {optionLabel(option)}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      );
    case "boolean":
      return (
        <NativeSelect
          {...control}
          className="w-full"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          <NativeSelectOption value="true">Yes</NativeSelectOption>
          <NativeSelectOption value="false">No</NativeSelectOption>
        </NativeSelect>
      );
    case "text":
      if (series.length > 0) {
        const listed = series.some((choice) => choice.id === value);
        return (
          <NativeSelect
            {...control}
            className="w-full"
            value={value}
            onChange={(event) => onChange(event.target.value)}
          >
            {listed ? null : (
              <NativeSelectOption value={value}>{value || "Choose a series"}</NativeSelectOption>
            )}
            {series.map((choice) => (
              <NativeSelectOption key={choice.id} value={choice.id}>
                {`${choice.id}: ${choice.title}`}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        );
      }
      return (
        <Input
          {...control}
          className="font-mono"
          value={value}
          autoComplete="off"
          spellCheck={false}
          onChange={(event) => onChange(event.target.value)}
        />
      );
    case "fixed":
      return null;
  }
}

/** A signal shown while the catalog that describes its kind is missing. */
function ReadOnlySignal({ row }: { row: SignalRow }) {
  return (
    <p className="rounded-lg border p-3 text-sm text-pretty">
      <code className="font-mono text-xs">{row.id}</code>:{" "}
      {row.original ? describeSignal(row.original) : row.type}
    </p>
  );
}

/** The schema's descriptions mark names as code with backticks: "Fewer than `lookback_months`." */
function withCode(text: string): React.ReactNode {
  return text.split(/`([^`]+)`/).map((part, index) =>
    index % 2 === 1 ? (
      <code key={index} className="font-mono">
        {part}
      </code>
    ) : (
      part
    ),
  );
}

/** "absolute" → "Absolute", "yoy_quarterly" → "Yoy quarterly". */
function optionLabel(option: string): string {
  const words = option.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
