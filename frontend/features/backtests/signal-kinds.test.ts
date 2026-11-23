import { describe, expect, it } from "vitest";

import { signalCatalog } from "@/features/backtests/fixtures/catalog-signals";
import { findKind, toSignalKinds } from "@/features/backtests/signal-kinds";

const { kinds } = toSignalKinds({ ok: true, value: signalCatalog });

describe("toSignalKinds", () => {
  it("lists the catalog's kinds in its order, named for people", () => {
    expect(kinds.map((kind) => [kind.type, kind.label])).toEqual([
      ["momentum", "Momentum"],
      ["revenue_growth", "Revenue growth"],
      ["revenue_growth_acceleration", "Revenue growth acceleration"],
      ["macro_change", "Macro change"],
    ]);
  });

  it("puts each description on one line", () => {
    expect(findKind(kinds, "momentum")?.description).toBe(
      "The total return over a lookback, leaving out the most recent months: 12-1 by default.",
    );
  });

  it("reads whole numbers with their bounds and defaults, in sentence case", () => {
    expect(findKind(kinds, "momentum")?.fields).toEqual([
      {
        name: "lookback_months",
        label: "Lookback months",
        description:
          "How many months back the return starts: 12, the default, for 12-1 momentum. At most 120.",
        required: false,
        kind: "integer",
        min: 1,
        max: 120,
        default: 12,
      },
      {
        name: "skip_months",
        label: "Skip months",
        description:
          "How many of the latest months to leave out: 1, the default, for 12-1 momentum. Fewer than `lookback_months`.",
        required: false,
        kind: "integer",
        min: 0,
        max: null,
        default: 1,
      },
    ]);
  });

  it("fixes a const, offers an enum's choices, and leaves a series as text", () => {
    expect(findKind(kinds, "revenue_growth_acceleration")?.fields).toEqual([
      expect.objectContaining({ name: "basis", kind: "fixed", value: "yoy_quarterly" }),
    ]);

    const macro = findKind(kinds, "macro_change")?.fields ?? [];
    expect(macro.map((field) => [field.name, field.kind, field.required])).toEqual([
      ["series", "text", true],
      ["releases", "integer", true],
      ["change", "choice", true],
    ]);
    expect(macro[2]).toMatchObject({ options: ["absolute", "relative"], default: null });
  });

  it("has no kinds when the catalog couldn't be loaded", () => {
    expect(toSignalKinds({ ok: false, failure: { kind: "unreachable" } })).toEqual({
      kinds: [],
      loaded: false,
    });
  });

  it("leaves out a parameter the form can't edit, such as a list", () => {
    // A kind the engine might add: one list parameter and one true-or-false.
    const added = toSignalKinds({
      ok: true,
      value: {
        spec_version: 1,
        data: [
          {
            type: "made_up",
            description: "A kind for this test.",
            parameters: {
              properties: {
                type: { const: "made_up", type: "string" },
                tickers: { type: "array", items: { type: "string" } },
                inverse: { type: "boolean", default: false, title: "Inverse" },
              },
              required: ["type"],
            },
          },
        ],
      },
    });
    expect(added.kinds[0].fields).toEqual([
      {
        name: "inverse",
        label: "Inverse",
        description: null,
        required: false,
        kind: "boolean",
        default: false,
      },
    ]);
  });
});
