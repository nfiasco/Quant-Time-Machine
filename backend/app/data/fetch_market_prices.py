import yfinance as yf
import pandas as pd
import os

TICKERS = ["AAPL", "MSFT", "JPM", "JNJ", "XOM"]
START_DATE = "2010-01-01"
END_DATE   = "2015-12-31"

def fetch_market_prices(tickers, start, end):
    print("Fetching market prices...")
    all_data = []

    for ticker in tickers:
        print(f"  Pulling {ticker}...")
        raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
        raw = raw.reset_index()
        raw.columns = [col[0] if isinstance(col, tuple) else col for col in raw.columns]

        df = pd.DataFrame({
            "ticker":         ticker,
            "date":           pd.to_datetime(raw["Date"]).dt.strftime("%Y-%m-%d"),
            "open":           raw["Open"].round(4),
            "high":           raw["High"].round(4),
            "low":            raw["Low"].round(4),
            "close":          raw["Close"].round(4),
            "volume":         raw["Volume"].astype(int),
            "available_date": pd.to_datetime(raw["Date"]).dt.strftime("%Y-%m-%d")
        })
        all_data.append(df)
        print(f"    {len(df)} rows")

    result = pd.concat(all_data, ignore_index=True)
    result = result.sort_values(["ticker", "date"]).reset_index(drop=True)
    return result

def get_prices_as_of(df, ticker, as_of_date):
    return df[
        (df["ticker"] == ticker) &
        (df["available_date"] <= as_of_date)
    ]

if __name__ == "__main__":
    df = fetch_market_prices(TICKERS, START_DATE, END_DATE)

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", "market_prices.csv")
    df.to_csv(output_path, index=False)
    print(f"\nSaved {len(df)} rows to {output_path}")
    print(df.head(3).to_string())

    print("\n--- Point-in-time filter test ---")
    before = get_prices_as_of(df, "AAPL", "2010-06-01")
    after  = get_prices_as_of(df, "AAPL", "2015-12-31")
    print(f"AAPL rows as of 2010-06-01: {len(before)}")
    print(f"AAPL rows as of 2015-12-31: {len(after)}")
    print("Filter working correctly" if len(before) < len(after) else "Something is wrong")
