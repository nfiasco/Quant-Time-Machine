"""Upload the sample CSVs to Supabase tables, for testing purposes.

Run from backend/, after the fetch_* scripts:
`uv run --with supabase python -m app.data.upload_to_supabase`.
It reads the CSVs from DATA_DIR/samples/ and needs SUPABASE_URL and SUPABASE_KEY
in backend/.env. The tables must already exist in the Supabase project.

The API doesn't read these tables: it serves point-in-time data from the Parquet
store (decision D1, doc/storage.md).
"""

import os

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

from app.config import BACKEND_DIR, get_settings

load_dotenv(BACKEND_DIR / ".env", override=False)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def upload_table(supabase, csv_file: str, table_name: str) -> None:
    csv_path = get_settings().data_dir / "samples" / csv_file
    df = pd.read_csv(csv_path)
    records = df.to_dict("records")

    print(f"Uploading {len(records)} rows to {table_name}...")

    batch_size = 500
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        supabase.table(table_name).upsert(batch).execute()
        print(f"  {min(i + batch_size, len(records))}/{len(records)} rows done")

    print(f"  {table_name} complete\n")


if __name__ == "__main__":
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise SystemExit("SUPABASE_URL and SUPABASE_KEY must be set in backend/.env.")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    upload_table(supabase, "market_prices.csv", "market_prices")
    upload_table(supabase, "company_filings.csv", "company_filings")
    upload_table(supabase, "economic_data.csv", "economic_data")

    print("All tables uploaded successfully.")
