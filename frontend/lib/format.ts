// Number formatting. Like lib/time.ts for times: fixed en-US formats, so the server and
// every browser print the same thing whatever the viewer's locale. Never format numbers
// for display with toLocaleString() or a bare toFixed().

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const WHOLE_USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const WHOLE = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const GROUPED = new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 });
const ONE_DECIMAL = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const TWO_DECIMALS = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const UP_TO_TWO_DECIMALS = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

const MINUS = "−";

/** A price, for example "$322.32". */
export function formatUsd(value: number): string {
  return USD.format(value);
}

/**
 * A large dollar amount in millions, as filings report it, for example "$58,313 million".
 * Amounts under a million are written out ("$950,000").
 */
export function formatUsdMillions(value: number): string {
  const sign = value < 0 ? MINUS : "";
  const amount = Math.abs(value);
  if (amount < 1_000_000) return `${sign}${WHOLE_USD.format(amount)}`;
  return `${sign}$${WHOLE.format(amount / 1_000_000)} million`;
}

/** A number grouped in thousands, with up to three decimals, for example "133,326". */
export function formatNumber(value: number): string {
  return GROUPED.format(value);
}

/**
 * A macro value: "13.3%" for a series in percent, otherwise the number alone ("133,326"),
 * meant to be shown with the series' units. `null`, a value published as missing, is
 * "no value".
 */
export function formatMacroValue(value: number | null, units: string): string {
  if (value === null) return "no value";
  const number = formatNumber(value);
  return units.trim().toLowerCase() === "percent" ? `${number}%` : number;
}

/**
 * A fraction as a percentage with one decimal, as the API's returns and rates are
 * fractions: 0.185 is "18.5%". With `signed`, a gain also gets "+", so a return's sign
 * doesn't rest on its color (GUIDELINES.md §7). A loss always gets "−", and a value that
 * rounds to zero gets no sign. `decimals: 2` keeps a small rate apart: "0.34%".
 */
export function formatPercent(
  fraction: number,
  { signed = false, decimals = 1 }: { signed?: boolean; decimals?: 1 | 2 } = {},
): string {
  const percent = fraction * 100;
  const text = (decimals === 2 ? TWO_DECIMALS : ONE_DECIMAL).format(Math.abs(percent));
  if (Math.abs(percent) < 0.5 / 10 ** decimals) return `${text}%`;
  const sign = percent < 0 ? MINUS : signed ? "+" : "";
  return `${sign}${text}%`;
}

/** A ratio, such as a Sharpe ratio or a beta, with two decimals: "1.06", "−0.25". */
export function formatRatio(value: number): string {
  const text = TWO_DECIMALS.format(Math.abs(value));
  return value < 0 && Math.abs(value) >= 0.005 ? `${MINUS}${text}` : text;
}

/**
 * A difference between two fractions in percentage points, with two decimals: a revenue
 * growth rate that fell from 10% to 1.61% changed by −0.0839, "−8.39 pts". With `signed`
 * (the default), a rise gets "+". A value that rounds to zero gets no sign.
 */
export function formatPoints(difference: number, { signed = true } = {}): string {
  const points = difference * 100;
  const text = TWO_DECIMALS.format(Math.abs(points));
  if (Math.abs(points) < 0.005) return `${text} pts`;
  const sign = points < 0 ? MINUS : signed ? "+" : "";
  return `${sign}${text} pts`;
}

/**
 * Basis points, hundredths of a percent, with up to two decimals: "10 bps" for a spec's
 * `bps_per_trade` of 10, and "0.67 bps" for a trade that cost 0.0000671 of the portfolio
 * (pass `fraction * 10_000`).
 */
export function formatBps(bps: number): string {
  return `${UP_TO_TWO_DECIMALS.format(bps)} ${bps === 1 ? "bp" : "bps"}`;
}
