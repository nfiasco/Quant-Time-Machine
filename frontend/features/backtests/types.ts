// Experiment spec v1, as sketched in doc/roadmap.md §3.4: the JSON document that fully
// describes a backtest. The engine validates it with the models in
// backend/app/backtest/spec.py, and a backend test checks that both use the same
// fields and values, so change them together. Once the API publishes its OpenAPI
// schema, generate these types from it instead (S8.6).

// The signal library is documented in doc/reference/signals.md (S7.4).
export type SignalSpec =
  /** 12-1 momentum unless the spec says otherwise: lookback 12, skip 1. */
  | { type: "momentum"; lookback_months?: number; skip_months?: number }
  | { type: "revenue_growth"; basis: "yoy_quarterly" }
  | { type: "revenue_growth_acceleration"; basis: "yoy_quarterly" }
  | {
      type: "macro_change";
      /** A series in the macro catalog, such as UNRATE. */
      series: string;
      releases: number;
      change: "absolute" | "relative";
    };

export type FilterSpec = {
  signal: string;
  op: ">" | ">=" | "<" | "<=";
  value: number;
};

export type ExperimentSpec = {
  spec_version: 1;
  name: string;
  universe: { type: "point_in_time_list"; id: string };
  period: { start: string; end: string };
  schedule: {
    rebalance: "monthly";
    /** For example "first_trading_day 09:30 America/New_York". */
    decision: string;
    fill: "same_day_close" | "next_day_open";
  };
  signals: Record<string, SignalSpec>;
  filters: FilterSpec[];
  portfolio: {
    weighting: "equal" | "value";
    /** False for a long-short portfolio, which needs `rank`. */
    long_only: boolean;
    /**
     * Holds only the ends of a ranking of the securities that pass the filters:
     * doc/reference/portfolio.md (S7.5). Without one, all that pass are held.
     */
    rank?: { signal: string; quantiles: number; long: "top" | "bottom" } | null;
  };
  benchmark: string;
  costs: { bps_per_trade: number };
};
