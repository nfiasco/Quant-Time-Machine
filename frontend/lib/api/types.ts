// Response types for the research API v1, copied from doc/api-v1.md ("TypeScript types").
// Hand-written until S8.6 generates them from the OpenAPI schema. Keep them in step with
// the doc: features/time-machine/fixtures/ checks the snapshot's example against them
// with `satisfies`, so `next build` fails when they drift.

// Use V1Response<Filing | null> for a single item and V1Response<Filing[]> for a list,
// where [] means nothing was known yet.
export type V1Response<T> = {
  knowledge_time: string;
  data_version: string | null; // null only if the backend's store has no data version yet
  data: T;
  reason: string | null;
};

export type KnowledgeTime = {
  knowledge_time: string;
  data_version: string | null;
};

export type Provenance = {
  available_at: string;
  time_assumed: boolean;
  source: "alfred" | "edgar" | "tiingo" | "curated";
  source_ref: string;
};

export type MacroObservation = Provenance & {
  series_id: string;
  title: string;
  units: string;
  frequency: string;
  seasonal_adjustment: string;
  release: string;
  period: string;
  value: number | null;
  vintage_date: string;
};

export type PriceBar = Provenance & {
  ticker: string;
  cik: number | null;
  session_date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
};

export type Filing = Provenance & {
  ticker: string;
  cik: number;
  company_name: string;
  accession_number: string;
  form: string;
  is_amendment: boolean;
  amends: string | null;
  period_of_report: string | null;
  filing_date: string;
  document_url: string | null;
  index_url: string;
};

export type Fundamental = Provenance & {
  ticker: string;
  cik: number | null;
  metric: string; // revenue, net_income, eps_diluted, operating_cash_flow, total_assets, or shares_outstanding
  concept: string;
  unit: string;
  period_start: string | null; // null for an instant
  period_end: string;
  fiscal_year: number | null;
  fiscal_period: "Q1" | "Q2" | "Q3" | "Q4" | null;
  value: number;
  derived: boolean;
  accession_numbers: string[];
};

export type DateRange = { first: string; last: string };

export type CatalogSeries = {
  series_id: string;
  title: string;
  units: string;
  frequency: string;
  seasonal_adjustment: string;
  release: string;
  observations: DateRange | null;
  vintages: DateRange | null;
};

export type CatalogCompany = {
  ticker: string | null;
  name: string;
  cik: number | null;
  universe: string;
  added: string;
  prices: DateRange | null;
  filings: DateRange | null;
  fundamentals: DateRange | null;
};

// GET /v1/catalog/signals has no knowledge_time or data_version.
export type SignalCatalog = {
  spec_version: 1;
  data: { type: string; description: string; parameters: Record<string, unknown> }[];
};

export type FilingsByForm = {
  "10-K": Filing | null;
  "10-Q": Filing | null;
  "8-K": Filing | null;
};

export type Membership = Provenance & { universe: string; added: string };

export type UniverseChange = Provenance & {
  universe: string;
  change: "joins" | "leaves";
  effective: string;
};

/** The first bar after the knowledge time. It never carries prices: they weren't known yet. */
export type NextBar = { session_date: string; available_at: string };

export type SnapshotCompanyKnown = {
  ticker: string;
  cik: number | null;
  company_name: string;
  prices_withheld: boolean;
  latest_bar: PriceBar | null;
  latest_filings: FilingsByForm;
  latest_revenue: Fundamental | null;
  universes: Membership[];
};

export type SnapshotCompanyNotYetKnown = {
  ticker: string;
  next_bar: NextBar | null;
  next_filings: FilingsByForm;
  later_amendments: Filing[];
  later_revenue: Fundamental[];
  universe_changes: UniverseChange[];
};

export type Snapshot = {
  known: {
    companies: SnapshotCompanyKnown[];
    series: { series_id: string; latest: MacroObservation | null }[];
  };
  not_yet_known: {
    companies: SnapshotCompanyNotYetKnown[];
    series: { series_id: string; period: string | null; revisions: MacroObservation[] }[];
  };
};

// GET /v1/macro/{series_id}/revisions returns V1Response<MacroObservation[]>,
// GET /v1/catalog/series V1Response<CatalogSeries[]>, GET /v1/catalog/companies
// V1Response<CatalogCompany[]>, and GET /v1/snapshot V1Response<Snapshot>.

export type V1Error = {
  error: {
    code:
      | "invalid_request"
      | "unknown_ticker"
      | "unknown_series"
      | "prices_restricted"
      | "not_found"
      | "method_not_allowed"
      | "internal_error";
    message: string;
    details: { field: string; message: string }[];
  };
};

export type V1ErrorCode = V1Error["error"]["code"];
