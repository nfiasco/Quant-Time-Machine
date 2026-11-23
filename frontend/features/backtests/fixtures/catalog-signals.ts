import type { GetResponse } from "@/lib/api/types";

/**
 * GET /v1/catalog/signals, as the API documents it: the "spec_v1" example in its OpenAPI
 * schema, which backend/app/api/examples.py builds from the spec's own models
 * (`signal_types()`). `satisfies` makes `next build` fail if it no longer matches the route's
 * response type, which is generated from the same schema (lib/api/types.ts).
 *
 * To refresh it, from frontend/:
 *   jq '.paths["/v1/catalog/signals"].get.responses["200"].content["application/json"].examples.spec_v1.value' ../doc/reference/openapi.json
 */
export const signalCatalog = {
  spec_version: 1,
  data: [
    {
      type: "momentum",
      description:
        "The total return over a lookback, leaving out the most recent months: 12-1 by\ndefault.",
      parameters: {
        additionalProperties: false,
        description:
          "The total return over a lookback, leaving out the most recent months: 12-1 by\ndefault.",
        properties: {
          type: {
            const: "momentum",
            title: "Type",
            type: "string",
          },
          lookback_months: {
            default: 12,
            description:
              "How many months back the return starts: 12, the default, for 12-1 momentum. At\nmost 120.",
            maximum: 120,
            minimum: 1,
            title: "Lookback Months",
            type: "integer",
          },
          skip_months: {
            default: 1,
            description:
              "How many of the latest months to leave out: 1, the default, for 12-1 momentum.\nFewer than `lookback_months`.",
            minimum: 0,
            title: "Skip Months",
            type: "integer",
          },
        },
        required: ["type"],
        title: "MomentumSignal",
        type: "object",
      },
    },
    {
      type: "revenue_growth",
      description: "The latest quarter's revenue growth over the same quarter a year earlier.",
      parameters: {
        additionalProperties: false,
        description: "The latest quarter's revenue growth over the same quarter a year earlier.",
        properties: {
          type: {
            const: "revenue_growth",
            title: "Type",
            type: "string",
          },
          basis: {
            const: "yoy_quarterly",
            description: "Each quarter's growth over the same quarter a year earlier.",
            title: "Basis",
            type: "string",
          },
        },
        required: ["type", "basis"],
        title: "RevenueGrowthSignal",
        type: "object",
      },
    },
    {
      type: "revenue_growth_acceleration",
      description: "This quarter's year-over-year revenue growth minus last quarter's.",
      parameters: {
        additionalProperties: false,
        description: "This quarter's year-over-year revenue growth minus last quarter's.",
        properties: {
          type: {
            const: "revenue_growth_acceleration",
            title: "Type",
            type: "string",
          },
          basis: {
            const: "yoy_quarterly",
            description: "Each quarter's growth over the same quarter a year earlier.",
            title: "Basis",
            type: "string",
          },
        },
        required: ["type", "basis"],
        title: "RevenueGrowthAccelerationSignal",
        type: "object",
      },
    },
    {
      type: "macro_change",
      description:
        "A macro series' change over its latest releases, as published by the decision.\nIt's the same for every security, so a filter on it holds securities only while the\neconomy meets a condition, such as unemployment falling.",
      parameters: {
        additionalProperties: false,
        description:
          "A macro series' change over its latest releases, as published by the decision.\nIt's the same for every security, so a filter on it holds securities only while the\neconomy meets a condition, such as unemployment falling.",
        properties: {
          type: {
            const: "macro_change",
            title: "Type",
            type: "string",
          },
          series: {
            description: 'A series in the macro catalog, such as "UNRATE", the unemployment rate.',
            title: "Series",
            type: "string",
          },
          releases: {
            description:
              "How many releases back the change starts: 3 compares the latest observation with\nthe one three months before it, or three quarters for a quarterly series. At most\n120.",
            maximum: 120,
            minimum: 1,
            title: "Releases",
            type: "integer",
          },
          change: {
            description:
              '"absolute" subtracts, in the series\' units, such as percentage points for UNRATE.\n"relative" divides: 0.03 is 3%.',
            enum: ["absolute", "relative"],
            title: "Change",
            type: "string",
          },
        },
        required: ["type", "series", "releases", "change"],
        title: "MacroChangeSignal",
        type: "object",
      },
    },
  ],
} satisfies GetResponse<"/v1/catalog/signals">;
