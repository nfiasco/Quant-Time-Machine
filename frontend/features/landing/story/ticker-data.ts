// Tickers for the decorative wall behind the landing logo: universe v1's current members
// (backend/app/data/sources/universes.toml). Only the names are real; the wall's numbers
// are random, and the page says so.

export const WALL_TICKERS = [
  "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "LLY", "UNH",
  "MA", "XOM", "HD", "PG", "JNJ", "WMT", "BAC", "KO", "PEP", "ABBV",
  "CSCO", "MCD", "CAT", "IBM", "GS", "WFC", "C", "VZ", "PFE", "INTC",
  "AMD", "BA", "PYPL", "UBER", "ABNB", "CRWD", "PLTR", "LULU",
] as const;

export const WALL_ROWS = 18;
export const WALL_CELLS_PER_ROW = 10;

/** A row's tickers: the list rotated, so neighboring rows differ. */
export function rowTickers(row: number): string[] {
  const start = (row * 7) % WALL_TICKERS.length;
  return Array.from(
    { length: WALL_CELLS_PER_ROW },
    (_, i) => WALL_TICKERS[(start + i) % WALL_TICKERS.length],
  );
}

/** Seconds per loop: slow, and different for each row. */
export function rowDuration(row: number): number {
  return 90 + ((row * 37) % 60);
}
