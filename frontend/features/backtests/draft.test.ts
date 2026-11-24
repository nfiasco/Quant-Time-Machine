import { describe, expect, it } from "vitest";

import {
  addFilter,
  addSignal,
  canonicalJson,
  changeSignalKind,
  delistingFromLoss,
  delistingLoss,
  draftFromSpec,
  removeSignal,
  setLongOnly,
  setRanked,
  setSignalId,
  setSignalParam,
  specFromDraft,
  suggestSignalId,
} from "@/features/backtests/draft";
import { signalCatalog } from "@/features/backtests/fixtures/catalog-signals";
import { canonicalPreset } from "@/features/backtests/presets";
import { findKind, toSignalKinds, type SignalKind } from "@/features/backtests/signal-kinds";
import type { ExperimentSpec } from "@/features/backtests/types";

const { kinds } = toSignalKinds({ ok: true, value: signalCatalog });
// Two of the series in the macro catalog, in its order (GET /v1/catalog/series).
const choices = { series: ["UNRATE", "PAYEMS"] };

function kind(type: string): SignalKind {
  const found = findKind(kinds, type);
  if (!found) throw new Error(`No ${type} in the catalog`);
  return found;
}

/** The canonical example as the builder writes it: with its delisting default written out. */
const canonicalAsWritten: ExperimentSpec = {
  ...canonicalPreset.spec,
  delisting: { assumed_return: 0 },
};

// The canonical example's rows: s1 is rev_accel, s2 mom_12_1, and f3 and f4 their filters.
const canonical = () => draftFromSpec(canonicalPreset.spec, kinds);

describe("draftFromSpec and specFromDraft", () => {
  it("round-trip the canonical example", () => {
    expect(specFromDraft(canonical(), kinds)).toEqual(canonicalAsWritten);
  });

  it("keep a spec's signals as they are when the catalog couldn't be loaded", () => {
    const draft = draftFromSpec(canonicalPreset.spec, []);
    expect(specFromDraft(draft, [])).toEqual(canonicalAsWritten);
  });

  it("let IDs the builder would have suggested follow the parameters", () => {
    expect(canonical().signals.map((row) => [row.key, row.id, row.idEdited])).toEqual([
      ["s1", "rev_accel", false],
      ["s2", "mom_12_1", false],
    ]);
    const named = draftFromSpec(
      { ...canonicalPreset.spec, signals: { momentum: { type: "momentum" } }, filters: [] },
      kinds,
    );
    expect(named.signals[0]).toMatchObject({ id: "momentum", idEdited: true });
  });

  it("round-trip a ranked long-short portfolio, as a run's spec writes it", () => {
    const spec: ExperimentSpec = {
      ...canonicalAsWritten,
      portfolio: {
        weighting: "equal",
        long_only: false,
        rank: { signal: "mom_12_1", quantiles: 5, long: "top" },
      },
    };
    const draft = draftFromSpec(spec, kinds);
    expect(draft).toMatchObject({
      ranked: true,
      longOnly: false,
      rank: { signalKey: "s2", quantiles: "5", long: "top" },
    });
    expect(specFromDraft(draft, kinds)).toEqual(spec);
  });

  it("read a run's spec, which writes a missing ranking as null", () => {
    const spec = {
      ...canonicalAsWritten,
      portfolio: { ...canonicalAsWritten.portfolio, rank: null },
    };
    expect(draftFromSpec(spec, kinds).ranked).toBe(false);
  });
});

describe("editing signals", () => {
  it("renames a signal whose ID follows its parameters, and its filter follows", () => {
    const draft = setSignalParam(canonical(), "s2", kind("momentum"), "lookback_months", "6");
    const spec = specFromDraft(draft, kinds);
    expect(Object.keys(spec.signals)).toEqual(["rev_accel", "mom_6_1"]);
    expect(spec.signals.mom_6_1).toEqual({ type: "momentum", lookback_months: 6, skip_months: 1 });
    expect(spec.filters[1]).toEqual({ signal: "mom_6_1", op: ">", value: 0 });
  });

  it("keeps a typed ID, which filters follow", () => {
    let draft = setSignalId(canonical(), "s2", "momentum");
    draft = setSignalParam(draft, "s2", kind("momentum"), "lookback_months", "6");
    const spec = specFromDraft(draft, kinds);
    expect(Object.keys(spec.signals)).toEqual(["rev_accel", "momentum"]);
    expect(spec.filters[1].signal).toBe("momentum");
  });

  it("leaves a blank optional parameter out, for the API's default", () => {
    const draft = setSignalParam(canonical(), "s2", kind("momentum"), "skip_months", "");
    const spec = specFromDraft(draft, kinds);
    // The ID counts the blank as its default, 1.
    expect(spec.signals).toHaveProperty("mom_12_1", { type: "momentum", lookback_months: 12 });
  });

  it("leaves a filter without a signal when its signal is removed", () => {
    const spec = specFromDraft(removeSignal(canonical(), "s1"), kinds);
    expect(Object.keys(spec.signals)).toEqual(["mom_12_1"]);
    expect(spec.filters[0]).toEqual({ signal: "", op: ">", value: 0 });
  });

  it("adds a signal with its kind's defaults and an ID of its own", () => {
    let draft = addSignal(canonical(), kind("momentum"), choices);
    expect(draft.signals[2]).toMatchObject({
      key: "s5",
      id: "mom_12_1_2",
      type: "momentum",
      params: { lookback_months: "12", skip_months: "1" },
    });
    draft = addSignal(draft, kind("macro_change"), choices);
    expect(draft.signals[3]).toMatchObject({
      id: "unrate_chg_1",
      params: { series: "UNRATE", releases: "1", change: "absolute" },
    });
  });

  it("starts a signal changed to another kind over, and its filter stays on it", () => {
    const draft = changeSignalKind(canonical(), "s2", kind("macro_change"), choices);
    const spec = specFromDraft(draft, kinds);
    expect(spec.signals).toEqual({
      rev_accel: { type: "revenue_growth_acceleration", basis: "yoy_quarterly" },
      unrate_chg_1: { type: "macro_change", series: "UNRATE", releases: 1, change: "absolute" },
    });
    expect(spec.filters[1].signal).toBe("unrate_chg_1");
  });
});

describe("filters and the ranking", () => {
  it("adds a filter on the first signal", () => {
    const draft = addFilter(canonical());
    expect(draft.filters[2]).toEqual({ key: "f5", signalKey: "s1", op: ">", value: "0" });
  });

  it("turns the ranking on for a long-short portfolio, which holds its ends", () => {
    const spec = specFromDraft(setLongOnly(canonical(), false), kinds);
    expect(spec.portfolio).toEqual({
      weighting: "equal",
      long_only: false,
      rank: { signal: "rev_accel", quantiles: 5, long: "top" },
    });
  });

  it("starts a ranking on the first signal that differs between companies", () => {
    const draft = setRanked(
      changeSignalKind(canonical(), "s1", kind("macro_change"), choices),
      true,
    );
    expect(specFromDraft(draft, kinds).portfolio).toEqual({
      weighting: "equal",
      long_only: true,
      rank: { signal: "mom_12_1", quantiles: 5, long: "top" },
    });
  });
});

describe("canonicalJson", () => {
  it("doesn't care about the order of the signals, as a run's spec sorts them", () => {
    const sorted: ExperimentSpec = {
      ...canonicalAsWritten,
      signals: {
        mom_12_1: canonicalPreset.spec.signals.mom_12_1,
        rev_accel: canonicalPreset.spec.signals.rev_accel,
      },
    };
    expect(canonicalJson(sorted)).toBe(canonicalJson(canonicalAsWritten));
  });

  it("cares about the order of the filters", () => {
    const swapped = { ...canonicalAsWritten, filters: [...canonicalAsWritten.filters].reverse() };
    expect(canonicalJson(swapped)).not.toBe(canonicalJson(canonicalAsWritten));
  });
});

describe("suggestSignalId", () => {
  it("names signals as the canonical example does", () => {
    const momentum = { type: "momentum", params: { lookback_months: "12", skip_months: "1" } };
    expect(suggestSignalId(momentum, kind("momentum"), [])).toBe("mom_12_1");
    const acceleration = { type: "revenue_growth_acceleration", params: {} };
    expect(suggestSignalId(acceleration, kind("revenue_growth_acceleration"), [])).toBe(
      "rev_accel",
    );
  });

  it("names a macro change by its series, kind of change, and releases", () => {
    const params = { series: "UNRATE", releases: "3", change: "relative" };
    expect(suggestSignalId({ type: "macro_change", params }, kind("macro_change"), [])).toBe(
      "unrate_pct_3",
    );
  });

  it("falls back to the type, and adds a number when another signal has the ID", () => {
    expect(suggestSignalId({ type: "made_up", params: {} }, undefined, [])).toBe("made_up");
    const growth = { type: "revenue_growth", params: {} };
    expect(suggestSignalId(growth, kind("revenue_growth"), ["rev_growth", "rev_growth_2"])).toBe(
      "rev_growth_3",
    );
  });
});

describe("the delisting loss field", () => {
  it("shows the assumed return as a loss in percent", () => {
    expect(delistingLoss(undefined)).toBe("0");
    expect(delistingLoss({ assumed_return: -0.3 })).toBe("30");
    expect(delistingLoss({ assumed_return: -0.07 })).toBe("7");
    expect(delistingLoss({ assumed_return: -1 })).toBe("100");
  });

  it("turns the loss back into the assumed return", () => {
    expect(delistingFromLoss("30")).toEqual({ assumed_return: -0.3 });
    expect(delistingFromLoss("100")).toEqual({ assumed_return: -1 });
    expect(Object.is(delistingFromLoss("0").assumed_return, 0)).toBe(true);
    expect(delistingFromLoss(" ").assumed_return).toBeNaN();
  });
});
