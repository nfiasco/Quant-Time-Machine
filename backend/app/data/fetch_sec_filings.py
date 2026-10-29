"""Fetch revenue and net income from SEC EDGAR's XBRL company facts, for testing purposes.

Run from backend/: `uv run --with requests python -m app.data.fetch_sec_filings`.
It reads SEC_USER_AGENT through app.config (set it in backend/.env) and writes
company_filings.csv to DATA_DIR/samples/, which git ignores.

LIMITATIONS (see issue #64):
- available_date is the fact's `filed` date, with no time of day. A filing is
  public from its EDGAR acceptance time, which the supported pipeline uses (S5.4).
- A value appears once for every filing that reported it (a 10-Q repeats the
  same quarter a year earlier), so one period_end can have several rows.
- get_filings_as_of() is a coarse date filter for testing only. It does not
  enforce publication-time correctness. Do not promote this into the supported
  pipeline without timezone-aware available_at timestamps and PointInTimeView.
"""

import time

import pandas as pd
import requests

from app.config import get_settings

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


def sec_headers():
    # SEC refuses automated requests that don't name who is asking.
    user_agent = get_settings().sec_user_agent
    if not user_agent:
        raise SystemExit(
            "SEC_USER_AGENT isn't set. SEC refuses requests without a name "
            "and contact email; see backend/.env.example."
        )
    return {"User-Agent": user_agent}


def fetch_company_filings(ticker, cik, metrics):
    print(f"  Pulling {ticker}...")
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

    try:
        r = requests.get(url, headers=sec_headers())
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
                    "available_date": filed_date,  # a date, not EDGAR's acceptance time
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
    """Coarse date filter for testing only.

    Returns filings whose filed date is on or before as_of_date. It compares
    dates, not EDGAR acceptance times, so it does NOT enforce publication-time
    correctness.
    """
    return df[
        (df["ticker"] == ticker)
        & (df["metric"] == metric)
        & (df["available_date"] <= as_of_date)
    ].sort_values("period_end")


if __name__ == "__main__":
    print("Fetching SEC EDGAR filings...")
    df = fetch_all_filings(COMPANIES, METRICS)

    output_path = get_settings().data_dir / "samples" / "company_filings.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"\nSaved {len(df)} rows to {output_path}")
    print(df.head(5).to_string())

    # Check the coarse date filter
    print("\n--- Coarse date filter check ---")
    print("Question: Which AAPL revenue figures had been filed by 2015-12-31?")
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
