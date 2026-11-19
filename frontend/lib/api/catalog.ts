import { apiFetch } from "@/lib/api/client";
import type { GetResponse } from "@/lib/api/types";

// The catalogs (S8.5). Call them from the server, like every v1 endpoint: the API's CORS
// lets browsers in only from localhost:3000 and the production site. Like the snapshot, they
// skip Next's data cache: the API keeps each answer for its data version (api-v1.md,
// "Caching").

const asOfQuery = (asOf: string) => new URLSearchParams({ as_of: asOf }).toString();

/**
 * The members of each universe at a moment, under the tickers and names they used then,
 * in the API's order (by internal id). Before 2010 it's `[]` with a `reason`.
 */
export function getCatalogCompanies(asOf: string): Promise<GetResponse<"/v1/catalog/companies">> {
  return apiFetch<GetResponse<"/v1/catalog/companies">>(
    `/v1/catalog/companies?${asOfQuery(asOf)}`,
    { cache: "no-store" },
  );
}

/** Every series in the catalog, with how much of it was published by a moment. */
export function getCatalogSeries(asOf: string): Promise<GetResponse<"/v1/catalog/series">> {
  return apiFetch<GetResponse<"/v1/catalog/series">>(`/v1/catalog/series?${asOfQuery(asOf)}`, {
    cache: "no-store",
  });
}
