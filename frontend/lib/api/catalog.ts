import { apiFetch } from "@/lib/api/client";
import type { CatalogCompany, CatalogSeries, V1Response } from "@/lib/api/types";

// The catalogs (S8.5). Call them from the server, like every v1 endpoint: the API's CORS
// lets browsers in only from localhost:3000 and the production site.

const asOfQuery = (asOf: string) => new URLSearchParams({ as_of: asOf }).toString();

/**
 * The members of each universe at a moment, under the tickers and names they used then,
 * in the API's order (by internal id). Before 2010 it's `[]` with a `reason`.
 */
export function getCatalogCompanies(asOf: string): Promise<V1Response<CatalogCompany[]>> {
  return apiFetch<V1Response<CatalogCompany[]>>(
    `/v1/catalog/companies?${asOfQuery(asOf)}`,
    { cache: "no-store" },
  );
}

/** Every series in the catalog, with how much of it was published by a moment. */
export function getCatalogSeries(asOf: string): Promise<V1Response<CatalogSeries[]>> {
  return apiFetch<V1Response<CatalogSeries[]>>(`/v1/catalog/series?${asOfQuery(asOf)}`, {
    cache: "no-store",
  });
}
