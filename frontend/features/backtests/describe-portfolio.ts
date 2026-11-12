import type { ExperimentSpec } from "@/features/backtests/types";

type Portfolio = ExperimentSpec["portfolio"];

const WEIGHTING_LABELS: Record<Portfolio["weighting"], string> = {
  equal: "equal weight",
  value: "value weight",
};

/** The usual names for a ranking's parts. Any other count is spelled out. */
const QUANTILE_NAMES: Record<number, string> = {
  2: "half",
  3: "third",
  4: "quartile",
  5: "quintile",
  10: "decile",
};

function describeEnd(end: "top" | "bottom", quantiles: number): string {
  const name = QUANTILE_NAMES[quantiles];
  return name ? `${end} ${name}` : `${end} of ${quantiles} quantiles`;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * A spec's portfolio in plain language, for the spec summary: which of the securities
 * that pass the filters are held, and at what weights. Without a ranking, all of them
 * are. The rules are in doc/reference/portfolio.md (S7.5).
 */
export function describePortfolio(portfolio: Portfolio): string {
  const weighting = WEIGHTING_LABELS[portfolio.weighting];
  const rank = portfolio.rank;
  if (!rank) {
    return `${capitalize(weighting)}${portfolio.long_only ? ", long only" : ""}`;
  }

  const end = describeEnd(rank.long, rank.quantiles);
  if (portfolio.long_only) {
    return `${capitalize(end)} by ${rank.signal}, ${weighting}, long only`;
  }
  const other = rank.long === "top" ? "bottom" : "top";
  return `Long the ${end} by ${rank.signal} and short the ${other}, ${weighting}`;
}
