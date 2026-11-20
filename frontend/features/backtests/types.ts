// Experiment spec v1 (doc/roadmap.md §3.4): the JSON document that fully describes a
// backtest, and the body of POST /v1/backtests. These are the engine's own models
// (backend/app/backtest/spec.py), generated from the API's OpenAPI schema into
// lib/api/schema.ts (S8.6), so the two can't drift. Each field's description is there.
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];

export type ExperimentSpec = Schemas["ExperimentSpec"];

/** A signal from the library (doc/reference/signals.md, S7.4), told apart by its `type`. */
export type SignalSpec = ExperimentSpec["signals"][string];

export type FilterSpec = Schemas["FilterSpec"];
