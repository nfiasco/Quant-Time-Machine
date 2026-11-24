"use client";

import { FieldLegend, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { BuilderField, SectionError } from "@/features/backtests/builder-field";
import {
  setLongOnly,
  setRanked,
  type BuilderDraft,
  type RankEnd,
} from "@/features/backtests/draft";
import type { EditDraft, Section } from "@/features/backtests/field-errors";
import type { SpecErrors } from "@/features/backtests/validation";

const SECTIONS: readonly Section[] = ["portfolio"];

type PortfolioFieldsProps = {
  draft: BuilderDraft;
  errors: SpecErrors;
  onEdit: EditDraft;
};

/**
 * Which of the securities that pass the filters are held, and how
 * (doc/reference/portfolio.md): all of them, or one end of a ranking, long only or
 * long-short, at equal weights.
 */
export function PortfolioFields({ draft, errors, onEdit }: PortfolioFieldsProps) {
  const sectionError = errors.portfolio;

  return (
    <FieldSet
      aria-describedby={sectionError ? "bt-portfolio-error" : undefined}
      data-invalid-section={sectionError ? "" : undefined}
    >
      <FieldLegend>Portfolio</FieldLegend>
      <div className="grid gap-4 @xl/field-group:grid-cols-3">
        <BuilderField
          id="bt-hold"
          label="Hold"
          description="A ranking keeps one end of what passes, such as the top fifth."
        >
          {(control) => (
            <NativeSelect
              {...control}
              className="w-full"
              value={draft.ranked ? "ranked" : "all"}
              onChange={(event) =>
                onEdit(SECTIONS, (current) => setRanked(current, event.target.value === "ranked"))
              }
            >
              <NativeSelectOption value="all">Everything that passes</NativeSelectOption>
              <NativeSelectOption value="ranked">One end of a ranking</NativeSelectOption>
            </NativeSelect>
          )}
        </BuilderField>
        <BuilderField
          id="bt-positions"
          label="Positions"
          error={errors["portfolio.long_only"]}
          description="Long-short holds one end of the ranking and shorts the other."
        >
          {(control) => (
            <NativeSelect
              {...control}
              className="w-full"
              value={draft.longOnly ? "long_only" : "long_short"}
              onChange={(event) =>
                onEdit(SECTIONS, (current) =>
                  setLongOnly(current, event.target.value === "long_only"),
                )
              }
            >
              <NativeSelectOption value="long_only">Long only</NativeSelectOption>
              <NativeSelectOption value="long_short">Long-short</NativeSelectOption>
            </NativeSelect>
          )}
        </BuilderField>
        <BuilderField
          id="bt-weighting"
          label="Weighting"
          error={errors["portfolio.weighting"]}
          description="The engine weights holdings equally for now."
        >
          {(control) => (
            <NativeSelect
              {...control}
              className="w-full"
              value={draft.weighting}
              onChange={(event) => {
                const weighting = event.target.value as BuilderDraft["weighting"];
                onEdit(SECTIONS, (current) => ({ ...current, weighting }));
              }}
            >
              <NativeSelectOption value="equal">Equal weight</NativeSelectOption>
              <NativeSelectOption value="value" disabled>
                Value weight (not supported yet)
              </NativeSelectOption>
            </NativeSelect>
          )}
        </BuilderField>
      </div>

      {draft.ranked ? <RankFields draft={draft} errors={errors} onEdit={onEdit} /> : null}
      <SectionError id="bt-portfolio-error" error={sectionError} />
    </FieldSet>
  );
}

/** The ranking's signal, how many parts it's split into, and the end held long. */
function RankFields({ draft, errors, onEdit }: PortfolioFieldsProps) {
  const rankError = errors["portfolio.rank"];
  const chosen = draft.signals.some((row) => row.key === draft.rank.signalKey)
    ? draft.rank.signalKey
    : null;
  const edit = (patch: Partial<BuilderDraft["rank"]>) =>
    onEdit(SECTIONS, (current) => ({ ...current, rank: { ...current.rank, ...patch } }));

  return (
    <FieldSet
      className="rounded-lg border p-3"
      aria-describedby={rankError ? "bt-rank-error" : undefined}
      data-invalid-section={rankError ? "" : undefined}
    >
      <FieldLegend variant="label">Ranking</FieldLegend>
      <div className="grid gap-3 @xl/field-group:grid-cols-3">
        <BuilderField
          id="bt-rank-signal"
          label="Rank by"
          error={errors["portfolio.rank.signal"]}
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
              {draft.signals.map((row) => {
                // A macro change is the same for every company, so it can't order them.
                const macro = row.type === "macro_change";
                return (
                  <NativeSelectOption key={row.key} value={row.key} disabled={macro}>
                    {`${row.id || "(no ID)"}${macro ? " (same for all)" : ""}`}
                  </NativeSelectOption>
                );
              })}
            </NativeSelect>
          )}
        </BuilderField>
        <BuilderField
          id="bt-rank-quantiles"
          label="Parts"
          error={errors["portfolio.rank.quantiles"]}
          description="5 for quintiles, 10 for deciles."
          compact
        >
          {(control) => (
            <Input
              {...control}
              type="number"
              inputMode="numeric"
              min={2}
              max={100}
              step={1}
              className="font-mono tabular-nums"
              value={draft.rank.quantiles}
              onChange={(event) => edit({ quantiles: event.target.value })}
            />
          )}
        </BuilderField>
        <BuilderField
          id="bt-rank-long"
          label="Held long"
          error={errors["portfolio.rank.long"]}
          compact
        >
          {(control) => (
            <NativeSelect
              {...control}
              className="w-full"
              value={draft.rank.long}
              onChange={(event) => edit({ long: event.target.value as RankEnd })}
            >
              <NativeSelectOption value="top">The top: highest values</NativeSelectOption>
              <NativeSelectOption value="bottom">The bottom: lowest values</NativeSelectOption>
            </NativeSelect>
          )}
        </BuilderField>
      </div>
      <SectionError id="bt-rank-error" error={rankError} />
    </FieldSet>
  );
}
