// Names for the research API v1's types (doc/reference/api-v1.md). They are the API's own:
// `npm run api:types` generates lib/api/schema.ts from its OpenAPI schema,
// doc/reference/openapi.json, which a backend test keeps equal to its models (S8.6). Never
// edit schema.ts by hand: regenerate it after the schema changes, and add a name here when
// a page needs one.
import type { components, paths } from "@/lib/api/schema";

type Schemas = components["schemas"];

/** Every route the API answers a GET on, such as `"/v1/snapshot"`. */
export type GetPath = {
  [Path in keyof paths]: paths[Path] extends { get: object } ? Path : never;
}[keyof paths];

/**
 * The JSON body of a GET route's 200 response, such as `GetResponse<"/v1/snapshot">`. A
 * helper in lib/api/ declares its return type with it, so a renamed route or a changed model
 * fails `next build`.
 */
export type GetResponse<Path extends GetPath> = paths[Path]["get"] extends {
  responses: { 200: { content: { "application/json": infer Body } } };
}
  ? Body
  : never;

/** Every route the API answers a POST on. For now that's `"/v1/backtests"`. */
export type PostPath = {
  [Path in keyof paths]: paths[Path] extends { post: object } ? Path : never;
}[keyof paths];

/** The JSON body a POST route takes, such as the experiment spec for `"/v1/backtests"`. */
export type PostBody<Path extends PostPath> = paths[Path]["post"] extends {
  requestBody: { content: { "application/json": infer Body } };
}
  ? Body
  : never;

type JsonBody<Response> = Response extends { content: { "application/json": infer Body } }
  ? Body
  : never;

/**
 * The JSON body of a POST route's success (a 200, 201, or 202), such as
 * `PostResponse<"/v1/backtests">`, which answers 202 for a run it queued and 200 for one
 * already saved, with the same body. Declared like `GetResponse`, so a renamed route or a
 * changed model fails `next build`.
 */
export type PostResponse<Path extends PostPath> = paths[Path]["post"] extends {
  responses: infer Responses;
}
  ? JsonBody<Responses[Extract<keyof Responses, 200 | 201 | 202>]>
  : never;

// The envelope. Use V1Response<Filing | null> for a single item and V1Response<Filing[]> for
// a list, where [] means nothing was known yet. Each endpoint's own response type, such as
// GetResponse<"/v1/snapshot">, is one of these.
export type KnowledgeTime = Schemas["AsOfResponse"];
export type V1Response<T> = KnowledgeTime & { data: T; reason: string | null };

export type MacroObservation = Schemas["MacroObservation"];
export type PriceBar = Schemas["PriceBar"];
export type Filing = Schemas["Filing"];
export type Fundamental = Schemas["Fundamental"];

export type CatalogSeries = Schemas["CatalogSeries"];
export type CatalogCompany = Schemas["CatalogCompany"];
// GET /v1/catalog/signals has no knowledge_time or data_version.
export type SignalCatalog = Schemas["SignalCatalogResponse"];

export type FilingsByForm = Schemas["FilingsByForm"];
export type Membership = Schemas["Membership"];
export type UniverseChange = Schemas["UniverseChange"];
/** The first bar after the knowledge time. It never carries prices: they weren't known yet. */
export type NextBar = Schemas["NextBar"];
export type SnapshotCompanyKnown = Schemas["SnapshotCompanyKnown"];
export type SnapshotCompanyNotYetKnown = Schemas["SnapshotCompanyNotYetKnown"];
export type Snapshot = Schemas["Snapshot"];

// Backtests (S8.4). The spec a run is built from, ExperimentSpec, is in
// features/backtests/types.ts.
export type BacktestSubmitted = Schemas["BacktestSubmitted"];
export type BacktestRun = Schemas["BacktestRun"];
export type RunStatus = BacktestRun["status"];
export type BacktestProgress = Schemas["BacktestProgress"];
export type BacktestResult = Schemas["BacktestResult"];
export type BacktestMetrics = Schemas["BacktestMetrics"];
export type BacktestPeriod = Schemas["BacktestPeriod"];
export type BacktestWarning = Schemas["BacktestWarning"];
/** One session's open or close: which price, never what it was. */
export type PricePoint = Schemas["PricePoint"];
export type EquityPoint = Schemas["EquityPoint"];
export type BacktestAudit = Schemas["BacktestAudit"];
export type AuditView = Schemas["AuditView"];
export type AuditTable = Schemas["AuditTable"];
export type BacktestHoldings = Schemas["BacktestHoldings"];
export type BacktestHolding = Schemas["BacktestHolding"];
export type BacktestTrades = Schemas["BacktestTrades"];
export type BacktestTrade = Schemas["BacktestTrade"];
export type BacktestCoverage = Schemas["BacktestCoverage"];
export type CoverageReport = Schemas["CoverageReport"];
export type CoverageCounts = Schemas["CoverageCounts"];
export type CoverageRow = Schemas["CoverageRow"];
export type CoverageExit = Schemas["CoverageExit"];

// The body of every error the API itself answers with, which `isV1Error` (lib/api/errors.ts)
// tells apart from a proxy's.
export type V1Error = Schemas["ErrorResponse"];
export type V1ErrorCode = Schemas["ErrorBody"]["code"];
