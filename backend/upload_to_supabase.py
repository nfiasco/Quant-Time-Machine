"""Upload sample CSVs to Supabase tables."""

import os

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "data", "samples")


def upload_table(supabase, csv_file: str, table_name: str) -> None:
    csv_path = os.path.join(SAMPLES_DIR, csv_file)
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
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    upload_table(supabase, "market_prices.csv", "market_prices")
    upload_table(supabase, "company_filings.csv", "company_filings")
    upload_table(supabase, "economic_data.csv", "economic_data")

    print("All tables uploaded successfully.")