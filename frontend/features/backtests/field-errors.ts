// Where the builder shows each problem with a spec. The API's 422 errors and the builder's
// own checks (validation.ts) name a field by its path in the spec, such as
// "signals.mom_12_1.lookback_months" or "filters.1.signal". The form shows an error beside
// the field or section with that path; these place the API's errors there, and put the rest,
// such as "spec", in the form's alert.

import type { BuilderDraft } from "@/features/backtests/draft";
import { findKind, type SignalKind } from "@/features/backtests/signal-kinds";
import type { SpecErrors } from "@/features/backtests/validation";

/** One invalid field in a 422, as `ApiFailure.details` holds it. */
export type FieldProblem = { field: string; message: string };

/** The parts of the spec the form has a section for: the first part of a path. */
export type Section =
  | "name"
  | "universe"
  | "period"
  | "schedule"
  | "signals"
  | "filters"
  | "portfolio"
  | "benchmark"
  | "costs"
  | "delisting";

/**
 * How a part of the form changes the draft: the sections the change touches, whose errors
 * from the API no longer hold, and the change itself.
 */
export type EditDraft = (
  sections: readonly Section[],
  change: (draft: BuilderDraft) => BuilderDraft,
) => void;

/** Paths with one control under them, whose errors show at that control. */
const ALIASES: Partial<Record<string, string>> = {
  universe: "universe.id",
  "universe.type": "universe.id",
  "schedule.rebalance": "schedule",
  costs: "costs.bps_per_trade",
  delisting: "delisting.assumed_return",
};

/**
 * Every path the form shows an error at for a draft: each field, and the sections that show
 * an error for the whole of themselves (`period`, `schedule`, `signals`, `filters`,
 * `portfolio`, and `portfolio.rank`).
 */
export function errorSlots(draft: BuilderDraft, kinds: readonly SignalKind[]): Set<string> {
  const slots = new Set([
    "name",
    "universe.id",
    "period",
    "period.start",
    "period.end",
    "schedule",
    "schedule.decision",
    "schedule.fill",
    "signals",
    "filters",
    "portfolio",
    "portfolio.weighting",
    "portfolio.long_only",
    "benchmark",
    "costs.bps_per_trade",
    "delisting.assumed_return",
  ]);
  for (const row of draft.signals) {
    slots.add(`signals.${row.id}`);
    slots.add(`signals.${row.id}.type`);
    for (const field of findKind(kinds, row.type)?.fields ?? []) {
      if (field.kind !== "fixed") slots.add(`signals.${row.id}.${field.name}`);
    }
  }
  draft.filters.forEach((_, index) => {
    for (const part of ["signal", "op", "value"]) slots.add(`filters.${index}.${part}`);
  });
  if (draft.ranked) {
    for (const path of ["rank", "rank.signal", "rank.quantiles", "rank.long"]) {
      slots.add(`portfolio.${path}`);
    }
  }
  return slots;
}

/**
 * The API's field errors by where the form shows them: at the field's own path, at its
 * alias, or else at its nearest enclosing section ("filters.1" at "filters"). What has no
 * place in the form, such as a body that isn't JSON ("spec"), goes in `other`. The first
 * message for a place wins.
 */
export function placeErrors(
  problems: readonly FieldProblem[],
  slots: ReadonlySet<string>,
): { fields: SpecErrors; other: string[] } {
  const fields: SpecErrors = {};
  const other: string[] = [];
  for (const { field, message } of problems) {
    const slot = slotOf(field, slots);
    if (slot === null) other.push(message);
    else fields[slot] ??= message;
  }
  return { fields, other };
}

/**
 * The errors that still hold once fields in these sections change. An edit can fix more
 * than its own field (a new start date fixes "period.end must be after period.start"), so
 * the whole section's messages go.
 */
export function withoutSections(errors: SpecErrors, sections: readonly Section[]): SpecErrors {
  const kept: SpecErrors = {};
  for (const [path, message] of Object.entries(errors)) {
    if (!(sections as readonly string[]).includes(path.split(".")[0])) kept[path] = message;
  }
  return kept;
}

function slotOf(path: string, slots: ReadonlySet<string>): string | null {
  for (
    let current = path;
    current;
    current = current.slice(0, Math.max(0, current.lastIndexOf(".")))
  ) {
    const slot = ALIASES[current] ?? current;
    if (slots.has(slot)) return slot;
  }
  return null;
}
