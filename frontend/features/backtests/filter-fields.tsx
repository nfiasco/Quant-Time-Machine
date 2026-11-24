"use client";

import { PlusIcon, Trash2Icon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { FieldDescription, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { BuilderField, SectionError } from "@/features/backtests/builder-field";
import {
  addFilter,
  removeFilter,
  updateFilter,
  type BuilderDraft,
  type FilterOp,
  type FilterRow,
} from "@/features/backtests/draft";
import type { EditDraft, Section } from "@/features/backtests/field-errors";
import type { SpecErrors } from "@/features/backtests/validation";

const SECTIONS: readonly Section[] = ["filters"];
const ADD_ID = "bt-add-filter";

const OPS: readonly { op: FilterOp; label: string }[] = [
  { op: ">", label: "> above" },
  { op: ">=", label: "≥ at least" },
  { op: "<", label: "< below" },
  { op: "<=", label: "≤ at most" },
];

type FilterFieldsProps = {
  draft: BuilderDraft;
  errors: SpecErrors;
  onEdit: EditDraft;
};

/** The spec's filters: conditions on signals that every holding meets at a decision. */
export function FilterFields({ draft, errors, onEdit }: FilterFieldsProps) {
  const sectionError = errors.filters;
  const noSignals = draft.signals.length === 0;

  return (
    <FieldSet
      aria-describedby={sectionError ? "bt-filters-error" : "bt-filters-description"}
      data-invalid-section={sectionError ? "" : undefined}
    >
      <FieldLegend>Filters</FieldLegend>
      <FieldDescription id="bt-filters-description">
        Conditions every holding meets at a decision, all of them. Values are in the signal&apos;s
        units: returns and growth are fractions, so 0.05 is 5%, and an absolute macro change is in
        its series&apos; units.
      </FieldDescription>

      {draft.filters.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {draft.filters.map((filter, index) => (
            <li key={filter.key}>
              <FilterRowFields
                filter={filter}
                index={index}
                draft={draft}
                errors={errors}
                onEdit={onEdit}
              />
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">
          No filters: every member of the universe passes.
        </p>
      )}
      <SectionError id="bt-filters-error" error={sectionError} />

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Button
          id={ADD_ID}
          type="button"
          variant="outline"
          size="sm"
          disabled={noSignals}
          aria-describedby={noSignals ? "bt-add-filter-help" : undefined}
          onClick={() => onEdit(SECTIONS, addFilter)}
        >
          <PlusIcon data-icon="inline-start" />
          Add a filter
        </Button>
        {noSignals ? (
          <p id="bt-add-filter-help" className="text-xs text-muted-foreground">
            Add a signal first: a filter tests one.
          </p>
        ) : null}
      </div>
    </FieldSet>
  );
}

type FilterRowFieldsProps = {
  filter: FilterRow;
  index: number;
  draft: BuilderDraft;
  errors: SpecErrors;
  onEdit: EditDraft;
};

function FilterRowFields({ filter, index, draft, errors, onEdit }: FilterRowFieldsProps) {
  const path = `filters.${index}`;
  const prefix = `bt-filter-${filter.key}`;
  const context = `of filter ${index + 1}`;
  const chosen = draft.signals.some((row) => row.key === filter.signalKey)
    ? filter.signalKey
    : null;
  const edit = (patch: Partial<Omit<FilterRow, "key">>) =>
    onEdit(SECTIONS, (current) => updateFilter(current, filter.key, patch));

  return (
    <div className="relative grid gap-3 rounded-lg border p-3 @lg/field-group:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)_auto] @lg/field-group:items-start">
      <BuilderField
        id={`${prefix}-signal`}
        label="Signal"
        labelContext={context}
        error={errors[`${path}.signal`]}
        compact
      >
        {(control) => (
          <NativeSelect
            {...control}
            className="w-full font-mono"
            value={chosen ?? ""}
            onChange={(event) => edit({ signalKey: event.target.value || null })}
          >
            {chosen ? null : <NativeSelectOption value="">Choose a signal</NativeSelectOption>}
            {draft.signals.map((row) => (
              <NativeSelectOption key={row.key} value={row.key}>
                {row.id || "(no ID)"}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        )}
      </BuilderField>
      <BuilderField
        id={`${prefix}-op`}
        label="Condition"
        labelContext={context}
        error={errors[`${path}.op`]}
        compact
      >
        {(control) => (
          <NativeSelect
            {...control}
            className="w-full"
            value={filter.op}
            onChange={(event) => edit({ op: event.target.value as FilterOp })}
          >
            {OPS.map(({ op, label }) => (
              <NativeSelectOption key={op} value={op}>
                {label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        )}
      </BuilderField>
      <BuilderField
        id={`${prefix}-value`}
        label="Value"
        labelContext={context}
        error={errors[`${path}.value`]}
        compact
      >
        {(control) => (
          // No inputMode: a value can be negative, and a phone's number pad has no minus key.
          <Input
            {...control}
            type="number"
            step="any"
            className="font-mono tabular-nums"
            value={filter.value}
            onChange={(event) => edit({ value: event.target.value })}
          />
        )}
      </BuilderField>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        // In the row's corner while the fields stack; in its own column beside them after.
        className="absolute top-2 right-2 @lg/field-group:static @lg/field-group:mt-6"
        aria-label={`Remove filter ${index + 1}`}
        onClick={() => {
          onEdit(SECTIONS, (current) => removeFilter(current, filter.key));
          requestAnimationFrame(() => document.getElementById(ADD_ID)?.focus());
        }}
      >
        <Trash2Icon />
      </Button>
    </div>
  );
}
