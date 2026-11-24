// The builder's state while it's edited, and the experiment spec it stands for. The form
// edits a draft rather than a spec, because a spec can't hold what's half done: a number
// field that's blank, two signals that briefly share an ID, a filter whose signal was just
// removed. `specFromDraft` writes the spec the API gets, and `validateDraft`
// (validation.ts) says what's wrong with it, keyed by the API's own field paths.
//
// Rows have keys that stay put while their signal's ID changes. Filters and the ranking
// point at a signal's key, so renaming a signal carries them along, and removing one leaves
// them pointing at nothing, which validation reports.

import { fieldDefault, findKind, type SignalKind } from "@/features/backtests/signal-kinds";
import type { ExperimentSpec, FilterSpec, SignalSpec } from "@/features/backtests/types";

type Spec = ExperimentSpec;
export type FilterOp = FilterSpec["op"];
export type RankEnd = NonNullable<Spec["portfolio"]["rank"]>["long"];

export type SignalRow = {
  /** Stable while the row exists: React's key, and what filters and the ranking point at. */
  key: string;
  /** The signal's ID in the spec, such as "mom_12_1". */
  id: string;
  /** False while the ID follows the parameters (`suggestSignalId`), true once it's typed. */
  idEdited: boolean;
  type: string;
  /** Each parameter's value as its field holds it, by name. Numbers are kept as typed. */
  params: Record<string, string>;
  /** The signal as a spec had it, sent as is when the catalog can't describe its kind. */
  original: SignalSpec | null;
};

export type FilterRow = {
  key: string;
  /** The key of the signal it tests, or null. */
  signalKey: string | null;
  op: FilterOp;
  value: string;
};

export type BuilderDraft = {
  name: string;
  universe: string;
  start: string;
  end: string;
  /** The decisions' New York time, such as "09:30", or "" while the field is blank. */
  decisionTime: string;
  fill: Spec["schedule"]["fill"];
  signals: SignalRow[];
  filters: FilterRow[];
  /** True to hold only one end of a ranking, false to hold everything that passes. */
  ranked: boolean;
  rank: { signalKey: string | null; quantiles: string; long: RankEnd };
  longOnly: boolean;
  weighting: Spec["portfolio"]["weighting"];
  benchmark: string;
  /** Basis points per trade, as typed. */
  costs: string;
  /** What a holding that stops trading is assumed to lose after its last close, in percent. */
  delistingLoss: string;
  /** The number in the next new row's key: rows are "s1", "s2", … and "f1", "f2", …. */
  nextKey: number;
};

/**
 * The values a text parameter can take when a catalog lists them, by the parameter's name:
 * `series`, from the series catalog. A new signal starts with the first.
 */
export type ParamChoices = Partial<Record<string, readonly string[]>>;

const DECISION = /^first_trading_day ([01][0-9]|2[0-3]):([0-5][0-9]) America\/New_York$/;

/** "first_trading_day 09:30 America/New_York" → "09:30", or undefined if malformed. */
export function decisionTime(decision: string): string | undefined {
  const match = DECISION.exec(decision);
  return match ? `${match[1]}:${match[2]}` : undefined;
}

/** "09:30" → "first_trading_day 09:30 America/New_York". */
export function decisionFromTime(time: string): string {
  return `first_trading_day ${time} America/New_York`;
}

/**
 * A spec's assumed delisting return as the builder's loss field shows it, in percent:
 * -0.3 → "30". The field asks for a loss so that a phone's number pad, which often has
 * no minus key, can enter it.
 */
export function delistingLoss(delisting: Spec["delisting"]): string {
  const loss = -(delisting?.assumed_return ?? 0) * 100;
  // Rounding drops floating-point noise (-0.07 * 100 is 7.000000000000001), and
  // `|| 0` writes -0 as 0.
  return String(Number(loss.toPrecision(12)) || 0);
}

/** The loss field's text as a spec's delisting section: "30" → -0.3. A blank field is
 * NaN, so it shows an error instead of becoming 0. */
export function delistingFromLoss(text: string): NonNullable<Spec["delisting"]> {
  const assumed = -numberOf(text) / 100;
  // A loss of 0 would be -0, which JSON writes as 0 anyway.
  return { assumed_return: assumed === 0 ? 0 : assumed };
}

/** A number field's text as a number: NaN when it's blank or not a number. */
export function numberOf(text: string): number {
  return text.trim() === "" ? Number.NaN : Number(text);
}

/** The draft a spec opens as, such as a preset's or an earlier run's. */
export function draftFromSpec(spec: Spec, kinds: readonly SignalKind[]): BuilderDraft {
  let next = 1;
  const keyOfId = new Map<string, string>();
  const signals: SignalRow[] = Object.entries(spec.signals).map(([id, signal]) => {
    const key = `s${next++}`;
    keyOfId.set(id, key);
    const kind = findKind(kinds, signal.type);
    const row = {
      key,
      id,
      type: signal.type,
      params: paramsOf(signal, kind),
      original: signal,
    };
    // An ID that's what the builder would suggest keeps following the parameters.
    return { ...row, idEdited: id !== suggestSignalId(row, kind, []) };
  });

  const filters: FilterRow[] = spec.filters.map((filter) => ({
    key: `f${next++}`,
    signalKey: keyOfId.get(filter.signal) ?? null,
    op: filter.op,
    value: String(filter.value),
  }));

  const rank = spec.portfolio.rank;
  return {
    name: spec.name,
    universe: spec.universe.id,
    start: spec.period.start,
    end: spec.period.end,
    decisionTime: decisionTime(spec.schedule.decision) ?? "",
    fill: spec.schedule.fill,
    signals,
    filters,
    ranked: Boolean(rank),
    rank: rank
      ? {
          signalKey: keyOfId.get(rank.signal) ?? null,
          quantiles: String(rank.quantiles),
          long: rank.long,
        }
      : { signalKey: null, quantiles: "5", long: "top" },
    longOnly: spec.portfolio.long_only,
    weighting: spec.portfolio.weighting,
    benchmark: spec.benchmark,
    costs: String(spec.costs.bps_per_trade),
    delistingLoss: delistingLoss(spec.delisting),
    nextKey: next,
  };
}

/**
 * The spec a draft stands for. Numbers that don't parse are NaN, and filters or a ranking
 * whose signal is gone name the signal "": validation reports both before anything is sent.
 * The delisting section is always written, since a run's ID doesn't change when a default
 * is written out.
 */
export function specFromDraft(draft: BuilderDraft, kinds: readonly SignalKind[]): Spec {
  const signals: Spec["signals"] = {};
  for (const row of draft.signals) signals[row.id] = signalOf(row, findKind(kinds, row.type));

  const portfolio: Spec["portfolio"] = { weighting: draft.weighting, long_only: draft.longOnly };
  if (draft.ranked) {
    portfolio.rank = {
      signal: signalIdOf(draft, draft.rank.signalKey),
      quantiles: numberOf(draft.rank.quantiles),
      long: draft.rank.long,
    };
  }

  return {
    spec_version: 1,
    name: draft.name,
    universe: { type: "point_in_time_list", id: draft.universe },
    period: { start: draft.start, end: draft.end },
    schedule: {
      rebalance: "monthly",
      decision: decisionFromTime(draft.decisionTime),
      fill: draft.fill,
    },
    signals,
    filters: draft.filters.map((filter) => ({
      signal: signalIdOf(draft, filter.signalKey),
      op: filter.op,
      value: numberOf(filter.value),
    })),
    portfolio,
    benchmark: draft.benchmark,
    costs: { bps_per_trade: numberOf(draft.costs) },
    delisting: delistingFromLoss(draft.delistingLoss),
  };
}

/**
 * A spec as JSON with every object's keys sorted, as the API hashes it: the order of the
 * signals doesn't matter, and the order of the filters does. Two specs with the same
 * canonical JSON are the same run on the same data.
 */
export function canonicalJson(spec: Spec): string {
  return JSON.stringify(spec, (_key, value: unknown) =>
    typeof value === "object" && value !== null && !Array.isArray(value)
      ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)))
      : value,
  );
}

/** The ID of the signal a key points at, or "" when there's none. */
export function signalIdOf(draft: BuilderDraft, key: string | null): string {
  return draft.signals.find((row) => row.key === key)?.id ?? "";
}

/**
 * The ID the builder gives a signal: "mom_12_1" for 12-1 momentum, "rev_accel",
 * "rev_growth", "unrate_chg_3" for UNRATE's absolute change over 3 releases (or
 * "unrate_pct_3" for a relative one), and otherwise its type. A blank optional parameter
 * counts as its default. If another signal has it, a number goes on the end: "mom_12_1_2".
 */
export function suggestSignalId(
  row: Pick<SignalRow, "type" | "params">,
  kind: SignalKind | undefined,
  taken: readonly string[],
): string {
  const value = (name: string) => {
    const text = row.params[name]?.trim() ?? "";
    if (text) return text;
    const field = kind?.fields.find((candidate) => candidate.name === name);
    const fallback = field ? fieldDefault(field) : null;
    return fallback === null ? "" : String(fallback);
  };
  const whole = (name: string) => (/^\d+$/.test(value(name)) ? String(Number(value(name))) : null);

  let base: string;
  switch (row.type) {
    case "momentum": {
      const lookback = whole("lookback_months");
      const skip = whole("skip_months");
      base = lookback !== null && skip !== null ? `mom_${lookback}_${skip}` : "mom";
      break;
    }
    case "revenue_growth":
      base = "rev_growth";
      break;
    case "revenue_growth_acceleration":
      base = "rev_accel";
      break;
    case "macro_change": {
      const series = slug(value("series"));
      const releases = whole("releases");
      const change = value("change") === "relative" ? "pct" : "chg";
      base = series ? [series, change, releases].filter(Boolean).join("_") : "macro";
      break;
    }
    default:
      base = slug(row.type) || "signal";
  }

  if (!taken.includes(base)) return base;
  for (let n = 2; ; n++) {
    const id = `${base}_${n}`;
    if (!taken.includes(id)) return id;
  }
}

/** A signal of a kind with its parameters' defaults, at the end of the list. */
export function addSignal(
  draft: BuilderDraft,
  kind: SignalKind,
  choices: ParamChoices,
): BuilderDraft {
  const params = freshParams(kind, choices);
  const id = suggestSignalId({ type: kind.type, params }, kind, idsBut(draft, null));
  const row: SignalRow = {
    key: `s${draft.nextKey}`,
    id,
    idEdited: false,
    type: kind.type,
    params,
    original: null,
  };
  return { ...draft, signals: [...draft.signals, row], nextKey: draft.nextKey + 1 };
}

/** Makes a signal another kind, with that kind's defaults. Filters on it stay. */
export function changeSignalKind(
  draft: BuilderDraft,
  key: string,
  kind: SignalKind,
  choices: ParamChoices,
): BuilderDraft {
  return updateSignal(draft, key, kind, (row) => ({
    ...row,
    type: kind.type,
    params: freshParams(kind, choices),
    original: null,
  }));
}

/** Sets one parameter. An ID the user hasn't typed follows it. */
export function setSignalParam(
  draft: BuilderDraft,
  key: string,
  kind: SignalKind | undefined,
  name: string,
  value: string,
): BuilderDraft {
  return updateSignal(draft, key, kind, (row) => ({
    ...row,
    params: { ...row.params, [name]: value },
    original: null,
  }));
}

/** Sets a signal's ID by hand: from then on it no longer follows the parameters. */
export function setSignalId(draft: BuilderDraft, key: string, id: string): BuilderDraft {
  return {
    ...draft,
    signals: draft.signals.map((row) => (row.key === key ? { ...row, id, idEdited: true } : row)),
  };
}

/** Removes a signal. Filters and a ranking on it are left without one, for the user to fix. */
export function removeSignal(draft: BuilderDraft, key: string): BuilderDraft {
  return { ...draft, signals: draft.signals.filter((row) => row.key !== key) };
}

/** A filter "> 0" on the first signal, at the end of the list. */
export function addFilter(draft: BuilderDraft): BuilderDraft {
  const filter: FilterRow = {
    key: `f${draft.nextKey}`,
    signalKey: draft.signals[0]?.key ?? null,
    op: ">",
    value: "0",
  };
  return { ...draft, filters: [...draft.filters, filter], nextKey: draft.nextKey + 1 };
}

export function updateFilter(
  draft: BuilderDraft,
  key: string,
  patch: Partial<Omit<FilterRow, "key">>,
): BuilderDraft {
  return {
    ...draft,
    filters: draft.filters.map((filter) => (filter.key === key ? { ...filter, ...patch } : filter)),
  };
}

export function removeFilter(draft: BuilderDraft, key: string): BuilderDraft {
  return { ...draft, filters: draft.filters.filter((filter) => filter.key !== key) };
}

/**
 * Holds one end of a ranking, or everything that passes the filters. A new ranking starts
 * on the first signal that differs between securities, so not a macro_change.
 */
export function setRanked(draft: BuilderDraft, ranked: boolean): BuilderDraft {
  const current = draft.signals.some((row) => row.key === draft.rank.signalKey);
  const signalKey = current
    ? draft.rank.signalKey
    : (draft.signals.find((row) => row.type !== "macro_change")?.key ?? null);
  return { ...draft, ranked, rank: { ...draft.rank, signalKey } };
}

/** Long only, or long-short, which holds a ranking's ends and so turns the ranking on. */
export function setLongOnly(draft: BuilderDraft, longOnly: boolean): BuilderDraft {
  const next = { ...draft, longOnly };
  return longOnly || draft.ranked ? next : setRanked(next, true);
}

function updateSignal(
  draft: BuilderDraft,
  key: string,
  kind: SignalKind | undefined,
  change: (row: SignalRow) => SignalRow,
): BuilderDraft {
  return {
    ...draft,
    signals: draft.signals.map((row) => {
      if (row.key !== key) return row;
      const changed = change(row);
      if (changed.idEdited) return changed;
      return { ...changed, id: suggestSignalId(changed, kind, idsBut(draft, key)) };
    }),
  };
}

/** The IDs of every signal but one, which a suggested ID mustn't repeat. */
function idsBut(draft: BuilderDraft, key: string | null): string[] {
  return draft.signals.filter((row) => row.key !== key).map((row) => row.id);
}

/** A new signal's parameters: each field's default, or the first of its choices. */
function freshParams(kind: SignalKind, choices: ParamChoices): Record<string, string> {
  const params: Record<string, string> = {};
  for (const field of kind.fields) {
    switch (field.kind) {
      case "fixed":
        break;
      case "integer":
      case "number":
        params[field.name] = textOf(field.default ?? (field.required ? field.min : null));
        break;
      case "choice":
        params[field.name] = field.default ?? field.options[0];
        break;
      case "text":
        params[field.name] = field.default ?? choices[field.name]?.[0] ?? "";
        break;
      case "boolean":
        params[field.name] = textOf(field.default ?? false);
        break;
    }
  }
  return params;
}

/** A spec's signal as the row's field values. Without its kind, every value but `type`. */
function paramsOf(signal: SignalSpec, kind: SignalKind | undefined): Record<string, string> {
  const values: Record<string, unknown> = signal;
  const params: Record<string, string> = {};
  if (!kind) {
    for (const [name, value] of Object.entries(values)) {
      if (name !== "type") params[name] = textOf(value);
    }
    return params;
  }
  for (const field of kind.fields) {
    if (field.kind !== "fixed") params[field.name] = textOf(values[field.name] ?? field.default);
  }
  return params;
}

/** The spec's object for a row. A blank optional parameter is left out, for its default. */
function signalOf(row: SignalRow, kind: SignalKind | undefined): SignalSpec {
  if (!kind) return row.original ?? ({ type: row.type } as SignalSpec);
  const signal: Record<string, unknown> = { type: row.type };
  for (const field of kind.fields) {
    if (field.kind === "fixed") {
      signal[field.name] = field.value;
      continue;
    }
    const text = row.params[field.name] ?? "";
    if (text.trim() === "" && !field.required) continue;
    signal[field.name] =
      field.kind === "integer" || field.kind === "number"
        ? numberOf(text)
        : field.kind === "boolean"
          ? text === "true"
          : text;
  }
  // The form can't prove the shape matches one of the spec's signals: validation and the
  // API check it, and the API names any field that's wrong.
  return signal as SignalSpec;
}

function textOf(value: unknown): string {
  return value === undefined || value === null ? "" : String(value);
}

/** "UNRATE" → "unrate"; anything but letters and digits becomes "_". */
function slug(text: string): string {
  const id = text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return /^[a-z]/.test(id) ? id : "";
}
