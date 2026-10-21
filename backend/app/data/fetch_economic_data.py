import os

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("FRED_API_KEY")

SERIES = {"UNRATE": "unemployment_rate", "CPIAUCSL": "inflation_cpi", "GDP": "gdp"}

START_DATE = "2010-01-01"
END_DATE = "2015-12-31"


def fetch_vintage_data(series_id, metric_name, start, end):
    print(f"  Pulling {series_id} ({metric_name})...")

    # Step 1 — get all vintage dates (dates when data was released/revised)
    url = "https://api.stlouisfed.org/fred/series/vintagedates"
    params = {
        "series_id": series_id,
        "api_key": API_KEY,
        "file_type": "json",
        "realtime_start": start,
        "realtime_end": end,
    }
    r = requests.get(url, params=params)
    vintage_dates = r.json().get("vintage_dates", [])
    print(f"    Found {len(vintage_dates)} vintage dates")

    # Step 2 — get observations as of each vintage date
    url2 = "https://api.stlouisfed.org/fred/series/observations"
    params2 = {
        "series_id": series_id,
        "api_key": API_KEY,
        "file_type": "json",
        "realtime_start": start,
        "realtime_end": end,
        "observation_start": start,
        "observation_end": end,
    }
    r2 = requests.get(url2, params=params2)
    observations = r2.json().get("observations", [])

    rows = []
    for obs in observations:
        if obs["value"] == ".":
            continue
        rows.append(
            {
                "series_id": series_id,
                "metric": metric_name,
                "observation_date": obs["date"],
                "value": float(obs["value"]),
                "vintage_date": obs["realtime_start"],
                "available_date": obs["realtime_start"],
            }
        )

    print(f"    {len(rows)} records")
    return rows


def fetch_all_economic(series, start, end):
    all_rows = []
    for series_id, metric_name in series.items():
        rows = fetch_vintage_data(series_id, metric_name, start, end)
        all_rows.extend(rows)
    return pd.DataFrame(all_rows)


def get_economic_as_of(df, series_id, as_of_date):
    """
    Point-in-time filter.
    Returns the value that was known for each observation_date
    as of the given date — not today's revised value.
    """
    filtered = df[(df["series_id"] == series_id) & (df["available_date"] <= as_of_date)]
    # For each observation date, take the most recent vintage known as of as_of_date
    return (
        filtered.sort_values("vintage_date")
        .groupby("observation_date")
        .last()
        .reset_index()
    )


if __name__ == "__main__":
    print("Fetching ALFRED economic data...")
    df = fetch_all_economic(SERIES, START_DATE, END_DATE)

    output_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "samples", "economic_data.csv"
    )
    df.to_csv(output_path, index=False)
    print(f"\nSaved {len(df)} rows to {output_path}")
    print(df.head(5).to_string())

    # Show the revision example
    print("\n--- Revision history example ---")
    unrate = df[df["series_id"] == "UNRATE"].sort_values(
        ["observation_date", "vintage_date"]
    )
    print(unrate[["observation_date", "value", "vintage_date"]].head(10).to_string())
    print(
        "\nSame observation_date, different values = data was revised after first release"
    )

    # Point-in-time filter test
    print("\n--- Point-in-time filter test ---")
    result = get_economic_as_of(df, "UNRATE", "2012-06-01")
    print(f"Unemployment values known as of 2012-06-01: {len(result)} rows")
    print(result.tail(3).to_string())
