// Client-side checks for the backtest builder: the rules in backend/app/backtest/spec.py
// that the form can check before sending, for instant feedback. The API stays the source of
// truth, and says what only it can, such as momentum's skip being shorter than its lookback
// or a period with no decision. Errors are keyed by the same dotted field paths as the API's
// 422 errors ("period.end", "signals.mom_12_1.lookback_months", "filters.1.signal"), so the
// form shows both in the same places (field-errors.ts).

import { decisionTime, specFromDraft, type BuilderDraft } from "@/features/backtests/draft";
import { findKind, type ParamField, type SignalKind } from "@/features/backtests/signal-kinds";
import type { ExperimentSpec } from "@/features/backtests/types";

export type SpecErrors = Partial<Record<string, string>>;

const TICKER = /^[A-Z0-9][A-Z0-9.-]*$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const SIGNAL_ID = /^[a-z][a-z0-9_]*$/;
/** The most parts a ranking can be split into: percentiles (spec.py's MAX_QUANTILES). */
const MAX_QUANTILES = 100;

/** Everything wrong with a draft that the form can tell before sending it. */
export function validateDraft(draft: BuilderDraft, kinds: readonly SignalKind[]): SpecErrors {
  return { ...validateSpec(specFromDraft(draft, kinds)), ...validateSignals(draft, kinds) };
}

/** The rules a spec breaks that don't need the signal catalog. */
export function validateSpec(spec: ExperimentSpec): SpecErrors {
  const errors: SpecErrors = {};

  if (!spec.name.trim()) {
    errors.name = "Name can't be blank.";
  }

  if (!DATE.test(spec.period.start)) {
    errors["period.start"] = "Enter a start date.";
  }
  if (!DATE.test(spec.period.end)) {
    errors["period.end"] = "Enter an end date.";
  } else if (DATE.test(spec.period.start) && spec.period.end <= spec.period.start) {
    errors["period.end"] = "End date must be after the start date.";
  }

  const time = decisionTime(spec.schedule.decision);
  if (!time) {
    errors["schedule.decision"] = "Enter a decision time.";
  } else if (spec.schedule.fill === "same_day_close" && time >= "16:00") {
    errors["schedule.decision"] =
      "A same-day close fill needs a decision before the 16:00 ET close. Decide earlier, or fill at the next day's open.";
  }

  spec.filters.forEach((filter, index) => {
    if (!hasSignal(spec, filter.signal)) {
      errors[`filters.${index}.signal`] = "Choose a signal.";
    }
    if (!Number.isFinite(filter.value)) {
      errors[`filters.${index}.value`] = "Enter a number.";
    }
  });

  const rank = spec.portfolio.rank;
  if (rank) {
    const ranked = hasSignal(spec, rank.signal) ? spec.signals[rank.signal] : undefined;
    if (!ranked) {
      errors["portfolio.rank.signal"] = "Choose a signal to rank by.";
    } else if (ranked.type === "macro_change") {
      errors["portfolio.rank.signal"] =
        `Rank by a signal that differs between companies: ${rank.signal}, a macro change, is the same for all of them.`;
    }
    if (!Number.isInteger(rank.quantiles) || rank.quantiles < 2 || rank.quantiles > MAX_QUANTILES) {
      errors["portfolio.rank.quantiles"] = `Enter a whole number from 2 to ${MAX_QUANTILES}.`;
    }
  } else if (!spec.portfolio.long_only) {
    errors["portfolio.long_only"] =
      "A long-short portfolio needs a ranking: it's long one end and short the other.";
  }

  if (!TICKER.test(spec.benchmark)) {
    errors.benchmark = "Enter a ticker in capitals, such as SPY.";
  }

  const bps = spec.costs.bps_per_trade;
  if (!Number.isFinite(bps)) {
    errors["costs.bps_per_trade"] = "Enter a number of basis points.";
  } else if (bps < 0) {
    errors["costs.bps_per_trade"] = "Costs must be at least 0.";
  }

  const assumed = spec.delisting?.assumed_return ?? 0;
  if (!Number.isFinite(assumed)) {
    errors["delisting.assumed_return"] = "Enter a loss from 0 to 100%.";
  } else if (assumed < -1 || assumed > 0) {
    errors["delisting.assumed_return"] = "The loss must be from 0 to 100%.";
  }

  return errors;
}

/**
 * Each signal's ID and parameters. The IDs are checked on the draft, since two signals with
 * one ID would be one in the spec. Parameters follow their schema from the catalog, so a
 * signal of a kind the catalog doesn't describe is left to the API.
 */
function validateSignals(draft: BuilderDraft, kinds: readonly SignalKind[]): SpecErrors {
  const errors: SpecErrors = {};
  const uses = new Map<string, number>();
  for (const row of draft.signals) uses.set(row.id, (uses.get(row.id) ?? 0) + 1);

  for (const row of draft.signals) {
    const path = `signals.${row.id}`;
    if (!row.id) {
      errors[path] = "Give the signal an ID.";
    } else if (!SIGNAL_ID.test(row.id)) {
      errors[path] = "Use lowercase letters, digits, and underscores, starting with a letter.";
    } else if ((uses.get(row.id) ?? 0) > 1) {
      errors[path] = "Another signal has this ID. Give each one its own.";
    }

    for (const field of findKind(kinds, row.type)?.fields ?? []) {
      const message = checkParam(field, row.params[field.name] ?? "");
      if (message) errors[`${path}.${field.name}`] = message;
    }
  }
  return errors;
}

/** What's wrong with a parameter's value, or null. A blank optional one takes its default. */
function checkParam(field: ParamField, text: string): string | null {
  const blank = text.trim() === "";
  switch (field.kind) {
    case "integer":
    case "number": {
      const what = field.kind === "integer" ? "a whole number" : "a number";
      if (blank) return field.required ? `Enter ${what}.` : null;
      const value = Number(text);
      if (!Number.isFinite(value) || (field.kind === "integer" && !Number.isInteger(value))) {
        return `Enter ${what}.`;
      }
      const { min, max } = field;
      if ((min !== null && value < min) || (max !== null && value > max)) {
        if (min !== null && max !== null) return `Enter ${what} from ${min} to ${max}.`;
        return min !== null
          ? `Enter ${what} of at least ${min}.`
          : `Enter ${what} of at most ${max}.`;
      }
      return null;
    }
    case "choice":
      if (blank) return field.required ? "Choose one." : null;
      return field.options.includes(text) ? null : "Choose one of the options.";
    case "text":
      return blank && field.required ? "Enter a value." : null;
    case "boolean":
    case "fixed":
      return null;
  }
}

/** True when the spec has a signal with this ID. A blank ID never names one. */
function hasSignal(spec: ExperimentSpec, id: string): boolean {
  return id !== "" && Object.hasOwn(spec.signals, id);
}
