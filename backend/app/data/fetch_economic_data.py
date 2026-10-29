"""Fetch ALFRED vintages of a few FRED series, for testing purposes.

Run from backend/: `uv run --with requests python -m app.data.fetch_economic_data`.
It reads FRED_API_KEY through app.config (set it in backend/.env) and writes
economic_data.csv to DATA_DIR/samples/, which git ignores.

LIMITATIONS (see issue #64):
- available_date is the vintage date, with no time of day. All three series
  are released at 08:30 ET, which the supported pipeline records (S4.3).
- get_economic_as_of() is a coarse date filter for testing only. It does not
  enforce publication-time correctness. Do not promote this into the supported
  pipeline without timezone-aware available_at timestamps and PointInTimeView.
"""

import pandas as pd
import requests

from app.config import get_settings

SERIES = {"UNRATE": "unemployment_rate", "CPIAUCSL": "inflation_cpi", "GDP": "gdp"}

START_DATE = "2010-01-01"
END_DATE = "2015-12-31"


def fred_api_key():
    key = get_settings().fred_api_key
    if key is None:
        raise SystemExit("FRED_API_KEY isn't set; see backend/.env.example.")
    return key.get_secret_value()


def fetch_vintage_data(series_id, metric_name, start, end):
    print(f"  Pulling {series_id} ({metric_name})...")

    # Step 1 — get all vintage dates (dates when data was released/revised)
    url = "https://api.stlouisfed.org/fred/series/vintagedates"
    params = {
        "series_id": series_id,
        "api_key": fred_api_key(),
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
        "api_key": fred_api_key(),
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
    """Coarse date filter for testing only.

    For each observation_date, returns the latest vintage dated on or before
    as_of_date. It compares dates, not release times, so it does NOT enforce
    publication-time correctness.
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

    output_path = get_settings().data_dir / "samples" / "economic_data.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
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

    # Coarse date filter check
    print("\n--- Coarse date filter check ---")
    result = get_economic_as_of(df, "UNRATE", "2012-06-01")
    print(f"Unemployment values dated on or before 2012-06-01: {len(result)} rows")
    print(result.tail(3).to_string())
