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
 * rounds to zero gets no sign.
 */
export function formatPercent(fraction: number, { signed = false } = {}): string {
  const percent = fraction * 100;
  const text = ONE_DECIMAL.format(Math.abs(percent));
  if (Math.abs(percent) < 0.05) return `${text}%`;
  const sign = percent < 0 ? MINUS : signed ? "+" : "";
  return `${sign}${text}%`;
}

/** A ratio, such as a Sharpe ratio or a beta, with two decimals: "1.06", "−0.25". */
export function formatRatio(value: number): string {
  const text = TWO_DECIMALS.format(Math.abs(value));
  return value < 0 && Math.abs(value) >= 0.005 ? `${MINUS}${text}` : text;
}
