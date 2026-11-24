import { describe, expect, it } from "vitest";

import { draftFromSpec, setRanked } from "@/features/backtests/draft";
import { errorSlots, placeErrors, withoutSections } from "@/features/backtests/field-errors";
import { signalCatalog } from "@/features/backtests/fixtures/catalog-signals";
import { canonicalPreset } from "@/features/backtests/presets";
import { toSignalKinds } from "@/features/backtests/signal-kinds";

const { kinds } = toSignalKinds({ ok: true, value: signalCatalog });
const draft = draftFromSpec(canonicalPreset.spec, kinds);
const slots = errorSlots(draft, kinds);

describe("placeErrors", () => {
  it("puts the API's documented 422 beside the benchmark and the costs", () => {
    // api-v1.md, POST /v1/backtests: "costs is required" names the section, whose only
    // field is its basis points.
    expect(
      placeErrors(
        [
          { field: "benchmark", message: "benchmark must be a ticker in capitals, such as SPY." },
          { field: "costs", message: "costs is required." },
        ],
        slots,
      ),
    ).toEqual({
      fields: {
        benchmark: "benchmark must be a ticker in capitals, such as SPY.",
        "costs.bps_per_trade": "costs is required.",
      },
      other: [],
    });
  });

  it("places a signal's parameter, a filter, and the engine's checks", () => {
    // The sentences backend/app/backtest/spec.py and simulation.py write for these paths.
    const problems = [
      {
        field: "signals.mom_12_1.skip_months",
        message: "signals.mom_12_1.skip_months must be less than lookback_months, 12.",
      },
      {
        field: "filters.1.signal",
        message: "filters.1.signal must name a signal in signals: 'rev_accel' or 'mom_12_1'.",
      },
      {
        field: "period",
        message:
          "period must include a decision whose trades fill before its last close, on 2020-01-17.",
      },
      {
        field: "portfolio.weighting",
        message: "portfolio.weighting must be 'equal' for now: value weights aren't supported yet.",
      },
    ];
    expect(placeErrors(problems, slots)).toEqual({
      fields: Object.fromEntries(problems.map(({ field, message }) => [field, message])),
      other: [],
    });
  });

  it("falls back to the nearest section the form has", () => {
    expect(
      placeErrors(
        [
          { field: "filters.5.value", message: "filters.5.value must be a number." },
          { field: "signals.gone.releases", message: "signals.gone.releases is required." },
        ],
        slots,
      ).fields,
    ).toEqual({
      filters: "filters.5.value must be a number.",
      signals: "signals.gone.releases is required.",
    });
  });

  it("shows a ranking's errors at its fields only while the form has a ranking", () => {
    const message = "portfolio.rank.quantiles must be at most 100.";
    const problem = { field: "portfolio.rank.quantiles", message };
    expect(placeErrors([problem], slots).fields).toEqual({ portfolio: message });
    const ranked = errorSlots(setRanked(draft, true), kinds);
    expect(placeErrors([problem], ranked).fields).toEqual({ "portfolio.rank.quantiles": message });
  });

  it("lists what the form has no place for, and keeps the first message for a place", () => {
    expect(
      placeErrors(
        [
          { field: "spec_version", message: "spec_version must be 1." },
          { field: "name", message: "name can't be blank." },
          { field: "name", message: "name must be a string." },
        ],
        slots,
      ),
    ).toEqual({ fields: { name: "name can't be blank." }, other: ["spec_version must be 1."] });
  });
});

describe("withoutSections", () => {
  it("drops every error in the sections that changed", () => {
    const errors = {
      "period.end": "period.end must be after period.start, 2020-01-01.",
      benchmark: "benchmark must be a ticker in capitals, such as SPY.",
      "signals.mom_12_1.skip_months": "signals.mom_12_1.skip_months must be less than 12.",
    };
    expect(withoutSections(errors, ["period", "signals"])).toEqual({
      benchmark: "benchmark must be a ticker in capitals, such as SPY.",
    });
  });
});
