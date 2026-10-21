import os
import time

import pandas as pd
import requests

# Same 5 companies, need their CIK numbers
COMPANIES = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "JPM": "0000019617",
    "JNJ": "0000200406",
    "XOM": "0000034088",
}

# Metrics to pull (these are the XBRL tag names SEC uses)
METRICS = {"Revenues": "revenue", "NetIncomeLoss": "net_income"}

HEADERS = {"User-Agent": "Elijah Jeudy elijah.jeudy10@gmail.com"}


def fetch_company_filings(ticker, cik, metrics):
    print(f"  Pulling {ticker}...")
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

    try:
        r = requests.get(url, headers=HEADERS)
        r.raise_for_status()
        facts = r.json()
    except requests.RequestException as e:
        print(f"    Error fetching {ticker}: {e}")
        return []

    rows = []
    gaap = facts.get("facts", {}).get("us-gaap", {})

    for xbrl_tag, metric_name in metrics.items():
        if xbrl_tag not in gaap:
            continue
        entries = gaap[xbrl_tag].get("units", {}).get("USD", [])

        for entry in entries:
            # Only want annual and quarterly filings
            form = entry.get("form", "")
            if form not in ["10-K", "10-Q"]:
                continue

            period_end = entry.get("end", "")
            filed_date = entry.get("filed", "")
            value = entry.get("val", None)

            # Filter to 2010-2015
            if not period_end.startswith(
                ("2010", "2011", "2012", "2013", "2014", "2015")
            ):
                continue

            rows.append(
                {
                    "ticker": ticker,
                    "metric": metric_name,
                    "period_end": period_end,
                    "filed_date": filed_date,
                    "available_date": filed_date,  # same thing — when it hit EDGAR
                    "value": value,
                    "form": form,
                }
            )

    print(f"    {len(rows)} records")
    return rows


def fetch_all_filings(companies, metrics):
    all_rows = []
    for ticker, cik in companies.items():
        rows = fetch_company_filings(ticker, cik, metrics)
        all_rows.extend(rows)
        time.sleep(0.5)  # be polite to SEC servers
    return pd.DataFrame(all_rows)


def get_filings_as_of(df, ticker, metric, as_of_date):
    """
    Point-in-time filter.
    Returns only filings that were publicly available on or before as_of_date.
    """
    return df[
        (df["ticker"] == ticker)
        & (df["metric"] == metric)
        & (df["available_date"] <= as_of_date)
    ].sort_values("period_end")


if __name__ == "__main__":
    print("Fetching SEC EDGAR filings...")
    df = fetch_all_filings(COMPANIES, METRICS)

    output_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "samples", "company_filings.csv"
    )
    df.to_csv(output_path, index=False)
    print(f"\nSaved {len(df)} rows to {output_path}")
    print(df.head(5).to_string())

    # Prove the filter works
    print("\n--- Point-in-time filter test ---")
    print("Question: What AAPL revenue was known on April 15, 2020?")
    result = get_filings_as_of(df, "AAPL", "revenue", "2015-12-31")
    print(
        result[["ticker", "metric", "period_end", "filed_date", "value"]]
        .tail(5)
        .to_string()
    )

    # Show the key example
    print("\n--- The money example ---")
    aapl = df[(df["ticker"] == "AAPL") & (df["metric"] == "revenue")].sort_values(
        "period_end"
    )
    print(
        aapl[["period_end", "filed_date", "available_date", "value", "form"]]
        .tail(8)
        .to_string()
    )
    print("\nNotice: period_end != filed_date. That gap is the whole project.")
