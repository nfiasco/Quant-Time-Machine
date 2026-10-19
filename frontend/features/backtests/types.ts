// Experiment spec v1, as sketched in doc/roadmap.md §3.4: the JSON document that fully
// describes a backtest. The engine validates it (S7.1). Once the API publishes its
// OpenAPI schema, generate these types from it instead (S8.6).

export type SignalSpec =
  | { type: "revenue_growth_acceleration"; basis: "yoy_quarterly" }
  | { type: "momentum"; lookback_months: number; skip_months: number };

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
  portfolio: { weighting: "equal" | "value"; long_only: boolean };
  benchmark: string;
  costs: { bps_per_trade: number };
};
