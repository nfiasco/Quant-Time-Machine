"use server";

import { catalogAsOf } from "@/features/time-machine/params";
import { toCompanyOptions, type CompanyOptions } from "@/features/time-machine/picker-options";
import { getCatalogCompanies } from "@/lib/api/catalog";
import { settle } from "@/lib/api/errors";
import { parseAsOf } from "@/lib/time";

/**
 * The ticker search's suggestions for a date other than the page's: the universe that
 * day, under the tickers used then (FB in 2020, META in 2023). The ticker picker calls it
 * when the form's date has changed. Returns null for a value that isn't a knowledge time;
 * a failed request comes back as options with a note.
 */
export async function loadCompanyOptions(asOf: unknown): Promise<CompanyOptions | null> {
  const moment = typeof asOf === "string" ? parseAsOf(asOf) : null;
  if (!moment) return null;
  const at = catalogAsOf(moment);
  return toCompanyOptions(at, await settle(getCatalogCompanies(at)));
}
