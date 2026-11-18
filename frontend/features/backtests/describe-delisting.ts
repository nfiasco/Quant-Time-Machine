import type { ExperimentSpec } from "@/features/backtests/types";
import { formatNumber } from "@/lib/format";

/**
 * A spec's delisting assumption in plain language, for the spec summary: what a holding
 * that stops trading is worth after its last close (doc/reference/portfolio.md, S6.7).
 * A spec without one keeps the last close's value.
 */
export function describeDelisting(delisting: ExperimentSpec["delisting"]): string {
  const assumed = delisting?.assumed_return ?? 0;
  if (!Number.isFinite(assumed)) return "—";
  if (assumed === 0) return "Valued at the last close";
  if (assumed <= -1) return "Written off";
  return `Valued at the last close less ${formatNumber(-assumed * 100)}%`;
}
