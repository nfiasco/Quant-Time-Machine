// What the Time Machine's pickers offer, built from the catalogs (S8.5). Plain data, so
// the page can hand it to the client form.

import type { Settled } from "@/lib/api/errors";
import type { CatalogCompany, CatalogSeries, V1Response } from "@/lib/api/types";

export type CompanyOption = { ticker: string; name: string };

/** The ticker search's suggestions: the universe's members at one moment. */
export type CompanyOptions = {
  /** The `as_of` these answer for, such as `2020-06-05T09:30`. */
  asOf: string;
  /** Sorted by ticker. */
  options: CompanyOption[];
  /** Why there are no suggestions, as a sentence to show, or null. */
  note: string | null;
};

export type SeriesOption = {
  id: string;
  title: string;
  /** Frequency, units, and release, for example "Monthly · Percent · Employment Situation". */
  detail: string;
};

/** The series picker's choices, in the catalog's order. */
export type SeriesOptions = {
  options: SeriesOption[];
  /** False when the catalog couldn't be loaded. */
  loaded: boolean;
};

/**
 * Suggestions from `GET /v1/catalog/companies`. Members without a ticker at that moment
 * can't be asked for by ticker, so they're left out; the rest are sorted by ticker
 * (the API lists them by internal id).
 */
export function toCompanyOptions(
  asOf: string,
  result: Settled<V1Response<CatalogCompany[]>>,
): CompanyOptions {
  if (!result.ok) {
    return {
      asOf,
      options: [],
      note: "Couldn't load the companies in the universe. You can still type a ticker.",
    };
  }

  const byTicker = new Map<string, CompanyOption>();
  for (const company of result.value.data) {
    if (company.ticker && !byTicker.has(company.ticker)) {
      byTicker.set(company.ticker, { ticker: company.ticker, name: company.name });
    }
  }
  const options = [...byTicker.values()].sort((a, b) =>
    a.ticker < b.ticker ? -1 : a.ticker > b.ticker ? 1 : 0,
  );
  return { asOf, options, note: options.length === 0 ? result.value.reason : null };
}

/** The series picker's choices from `GET /v1/catalog/series`. */
export function toSeriesOptions(result: Settled<V1Response<CatalogSeries[]>>): SeriesOptions {
  if (!result.ok) return { options: [], loaded: false };
  return {
    options: result.value.data.map((series) => ({
      id: series.series_id,
      title: series.title,
      detail: [series.frequency, series.units, series.release].filter(Boolean).join(" · "),
    })),
    loaded: true,
  };
}
