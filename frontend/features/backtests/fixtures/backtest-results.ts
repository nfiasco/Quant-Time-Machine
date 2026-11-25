import type { GetResponse } from "@/lib/api/types";

// A run's parts at its June 1, 2020 decision, as doc/reference/api-v1.md documents them,
// copied as they are. `satisfies` makes `next build` fail if one no longer matches its
// route's response type, which is generated from the API's own schema (lib/api/types.ts).

/**
 * GET /v1/backtests/4036…fed2/members?decision=2020-06-01: three of the canonical run's 40
 * members that day, ABBV held, AAPL failing rev_accel > 0, and KSS left out without rev_accel.
 */
export const membersJune = {
  run_id: "40365a9a819b04a02bfb31d1e915ff4127fa1ac830959b4b62eaf6f45a0afed2",
  status: "succeeded",
  members: [
    {
      decision: "2020-06-01",
      ticker: "ABBV",
      name: "AbbVie Inc.",
      cik: 1551152,
      outcome: "held",
      weight: 0.1,
      signals: {
        mom_12_1: 0.134527265701,
        rev_accel: 0.0530041743358,
      },
      reasons: {},
      missing: [],
      failed: [],
      rank: null,
    },
    {
      decision: "2020-06-01",
      ticker: "AAPL",
      name: "Apple Inc.",
      cik: 320193,
      outcome: "failed_filter",
      weight: null,
      signals: {
        mom_12_1: 0.693680328621,
        rev_accel: -0.0839275653488,
      },
      reasons: {},
      missing: [],
      failed: [0],
      rank: null,
    },
    {
      decision: "2020-06-01",
      ticker: "KSS",
      name: "Kohl's Corporation",
      cik: 885639,
      outcome: "missing_signal",
      weight: null,
      signals: {
        mom_12_1: -0.593996435012,
        rev_accel: null,
      },
      reasons: {
        rev_accel:
          "Revenue for the quarter a year before the one that ended on 2019-11-02 wasn't known.",
      },
      missing: ["rev_accel"],
      failed: [],
      rank: null,
    },
  ],
} satisfies GetResponse<"/v1/backtests/{run_id}/members">;

/**
 * GET /v1/backtests/9dfe…b30f/holdings?decision=2020-06-01: one of the ten holdings.
 */
export const holdingsJune = {
  run_id: "9dfedcfa918368dcbd3d3af6d83abe4496f4ea6ed475303da691b5b1dcb2b30f",
  status: "succeeded",
  holdings: [
    {
      decision: "2020-06-01",
      ticker: "ABBV",
      weight: 0.1,
      signals: {
        mom_12_1: 0.134527265701,
        rev_accel: 0.0530041743358,
      },
      period_return: 0.0930540242558,
      exit: {
        session: "2020-07-01",
        price: "close",
      },
    },
  ],
} satisfies GetResponse<"/v1/backtests/{run_id}/holdings">;

/**
 * GET /v1/backtests/9dfe…b30f/trades?decision=2020-06-01: one of the eleven trades.
 */
export const tradesJune = {
  run_id: "9dfedcfa918368dcbd3d3af6d83abe4496f4ea6ed475303da691b5b1dcb2b30f",
  status: "succeeded",
  trades: [
    {
      decision: "2020-06-01",
      ticker: "ABBV",
      fill: {
        session: "2020-06-01",
        price: "close",
      },
      weight_before: 0.167131629103,
      weight_after: 0.1,
      traded: 0.0671316291031,
      cost: 6.71316291031e-5,
    },
  ],
} satisfies GetResponse<"/v1/backtests/{run_id}/trades">;

/**
 * GET /v1/backtests/9dfe…b30f/audit?decision=2020-06-01: the decision's view, with two of its
 * six tables and one group each, Apple's among the XBRL facts.
 */
export const auditJune = {
  run_id: "9dfedcfa918368dcbd3d3af6d83abe4496f4ea6ed475303da691b5b1dcb2b30f",
  status: "succeeded",
  views: [
    {
      purpose: "decision",
      decision: "2020-06-01",
      knowledge_time: "2020-06-01T09:30:00-04:00",
      rows: 17732,
      tables: [
        {
          table: "macro_observations",
          rows: 1,
          earliest_available_at: "2020-05-01T16:15:00-04:00",
          latest_available_at: "2020-05-01T16:15:00-04:00",
          sha256: "086c65a3ca738ea073278cbd517f83509c3265004537b628a1524fdc503bd8b0",
          groups: [
            {
              key: "TB3MS",
              rows: 1,
              latest_available_at: "2020-05-01T16:15:00-04:00",
              latest_source_ref: "TB3MS vintage 2020-05-01",
            },
          ],
        },
        {
          table: "xbrl_facts",
          rows: 8249,
          earliest_available_at: "2009-07-22T12:32:52-04:00",
          latest_available_at: "2020-05-26T19:59:23-04:00",
          sha256: "0f793c68e90373a69ca5db2244484d4ec1130244d5633f8aab15f8bf223cbb48",
          groups: [
            {
              key: 320193,
              rows: 248,
              latest_available_at: "2020-04-30T18:03:10-04:00",
              latest_source_ref: "0000320193-20-000052",
            },
          ],
        },
      ],
    },
  ],
} satisfies GetResponse<"/v1/backtests/{run_id}/audit">;

/**
 * GET /v1/backtests/4036…fed2/coverage: the canonical run's report, with one of its 637 rows and
 * one of its three exits.
 */
export const canonicalCoverage = {
  run_id: "40365a9a819b04a02bfb31d1e915ff4127fa1ac830959b4b62eaf6f45a0afed2",
  status: "succeeded",
  coverage: {
    decisions: 192,
    totals: {
      member_decisions: 7529,
      left_out: 326,
      stopped_trading: 0,
      missing: {
        fundamentals: 312,
        prices: 25,
      },
      signals: {
        mom_12_1: 25,
        rev_accel: 312,
      },
      no_fill_price: 0,
      exits: 3,
    },
    rows: [
      {
        ticker: "XOM",
        name: "Exxon Mobil Corporation",
        year: 2010,
        member_decisions: 12,
        left_out: 12,
        stopped_trading: 0,
        missing: {
          fundamentals: 12,
          prices: 0,
        },
        signals: {
          mom_12_1: 0,
          rev_accel: 12,
        },
        no_fill_price: 0,
        exits: 0,
      },
    ],
    exits: [
      {
        decision: "2019-11-01",
        ticker: "CELG",
        kind: "delisted_exit",
        valued_at: {
          session: "2019-11-20",
          price: "close",
        },
        end: {
          session: "2019-12-02",
          price: "close",
        },
      },
    ],
  },
} satisfies GetResponse<"/v1/backtests/{run_id}/coverage">;
