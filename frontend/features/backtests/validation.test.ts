import { describe, expect, it } from "vitest";

import {
  changeSignalKind,
  draftFromSpec,
  removeSignal,
  setRanked,
  setSignalId,
  setSignalParam,
  type BuilderDraft,
} from "@/features/backtests/draft";
import { signalCatalog } from "@/features/backtests/fixtures/catalog-signals";
import { canonicalPreset } from "@/features/backtests/presets";
import { findKind, toSignalKinds } from "@/features/backtests/signal-kinds";
import type { ExperimentSpec } from "@/features/backtests/types";
import { validateDraft, validateSpec } from "@/features/backtests/validation";

const { kinds } = toSignalKinds({ ok: true, value: signalCatalog });
const momentum = findKind(kinds, "momentum");
const macroChange = findKind(kinds, "macro_change");

function withDelisting(assumed_return: number): ExperimentSpec {
  return { ...canonicalPreset.spec, delisting: { assumed_return } };
}

// The canonical example's rows: s1 is rev_accel, s2 mom_12_1, and f3 and f4 their filters.
const canonical = (): BuilderDraft => draftFromSpec(canonicalPreset.spec, kinds);

describe("validateSpec", () => {
  it("accepts the canonical example, which leaves the delisting rule out", () => {
    expect(validateSpec(canonicalPreset.spec)).toEqual({});
  });

  it("accepts a delisting loss from 0 to 100%", () => {
    for (const assumed of [0, -0.3, -1]) {
      expect(validateSpec(withDelisting(assumed))).toEqual({});
    }
  });

  it("rejects a delisting loss outside 0 to 100%, under the API's field path", () => {
    expect(validateSpec(withDelisting(-1.5))).toEqual({
      "delisting.assumed_return": "The loss must be from 0 to 100%.",
    });
    expect(validateSpec(withDelisting(0.1))).toEqual({
      "delisting.assumed_return": "The loss must be from 0 to 100%.",
    });
    expect(validateSpec(withDelisting(Number.NaN))).toEqual({
      "delisting.assumed_return": "Enter a loss from 0 to 100%.",
    });
  });

  it("needs a ranking for a long-short portfolio", () => {
    const spec: ExperimentSpec = {
      ...canonicalPreset.spec,
      portfolio: { weighting: "equal", long_only: false },
    };
    expect(validateSpec(spec)).toEqual({
      "portfolio.long_only":
        "A long-short portfolio needs a ranking: it's long one end and short the other.",
    });
  });

  it("checks the ranking's signal and parts", () => {
    const spec: ExperimentSpec = {
      ...canonicalPreset.spec,
      portfolio: {
        weighting: "equal",
        long_only: false,
        rank: { signal: "mom_6_1", quantiles: 1, long: "top" },
      },
    };
    expect(validateSpec(spec)).toEqual({
      "portfolio.rank.signal": "Choose a signal to rank by.",
      "portfolio.rank.quantiles": "Enter a whole number from 2 to 100.",
    });
  });
});

describe("validateDraft", () => {
  it("accepts the canonical example", () => {
    expect(validateDraft(canonical(), kinds)).toEqual({});
  });

  it("checks each signal's ID: blank, malformed, or shared", () => {
    expect(validateDraft(setSignalId(canonical(), "s1", ""), kinds)).toEqual({
      "signals.": "Give the signal an ID.",
      // Its filter now names a signal "", which never counts.
      "filters.0.signal": "Choose a signal.",
    });
    expect(validateDraft(setSignalId(canonical(), "s1", "Rev"), kinds)).toEqual({
      "signals.Rev": "Use lowercase letters, digits, and underscores, starting with a letter.",
    });
    expect(validateDraft(setSignalId(canonical(), "s1", "mom_12_1"), kinds)).toEqual({
      "signals.mom_12_1": "Another signal has this ID. Give each one its own.",
    });
  });

  it("checks parameters against their schema, under the signal's current ID", () => {
    const tooLong = setSignalParam(canonical(), "s2", momentum, "lookback_months", "121");
    expect(validateDraft(tooLong, kinds)).toEqual({
      "signals.mom_121_1.lookback_months": "Enter a whole number from 1 to 120.",
    });
    const fraction = setSignalParam(canonical(), "s2", momentum, "skip_months", "1.5");
    expect(validateDraft(fraction, kinds)).toEqual({
      "signals.mom.skip_months": "Enter a whole number.",
    });
  });

  it("needs a required parameter, but lets an optional one take its default", () => {
    const macro = changeSignalKind(canonical(), "s1", macroChange!, { series: ["UNRATE"] });
    const blank = setSignalParam(macro, "s1", macroChange, "releases", "");
    expect(validateDraft(blank, kinds)).toEqual({
      "signals.unrate_chg.releases": "Enter a whole number.",
    });
    const optional = setSignalParam(canonical(), "s2", momentum, "lookback_months", "");
    expect(validateDraft(optional, kinds)).toEqual({});
  });

  it("leaves rules between parameters, such as skip below lookback, to the API", () => {
    const draft = setSignalParam(canonical(), "s2", momentum, "skip_months", "12");
    expect(validateDraft(draft, kinds)).toEqual({});
  });

  it("reports a filter whose signal was removed", () => {
    expect(validateDraft(removeSignal(canonical(), "s1"), kinds)).toEqual({
      "filters.0.signal": "Choose a signal.",
    });
  });

  it("won't rank by a macro change, which is the same for every company", () => {
    let draft = setRanked(canonical(), true);
    draft = changeSignalKind(draft, "s1", macroChange!, { series: ["UNRATE"] });
    draft = { ...draft, rank: { ...draft.rank, signalKey: "s1" } };
    expect(validateDraft(draft, kinds)).toEqual({
      "portfolio.rank.signal":
        "Rank by a signal that differs between companies: unrate_chg_1, a macro change, is the same for all of them.",
    });
  });
});
