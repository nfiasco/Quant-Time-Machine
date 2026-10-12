# /// script
# requires-python = ">=3.14"
# dependencies = ["httpx==0.28.1", "python-dotenv==1.2.3"]
#
# [tool.uv]
# exclude-newer = "2026-10-12T00:00:00Z"
# ///
"""Spike S4.1: how ALFRED vintages work in practice.

Run from backend/:  uv run spikes/alfred.py
Needs FRED_API_KEY in backend/.env (see .env.example). Prints Markdown; saves nothing.

Questions it answers:
- January 1990 unemployment (UNRATE) as first published vs. as currently revised.
- What realtime_start/realtime_end, output_type, and series/vintagedates do.
- What a point-in-time ("as of") query looks like, using the June 5, 2020 example.
- How missing values and request limits show up.
- For the six starter series: when their data and their vintage history start, and whether
  their notes mention a third-party copyright (FRED's terms require the owner's permission then).
"""

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
API_KEY = os.environ.get("FRED_API_KEY", "")
if not API_KEY:
    sys.exit("Set FRED_API_KEY in backend/.env first (see backend/.env.example).")

ALL_TIME = {"realtime_start": "1776-07-04", "realtime_end": "9999-12-31"}
client = httpx.Client(base_url="https://api.stlouisfed.org/fred/", timeout=30)
last_headers: httpx.Headers = httpx.Headers()


def fred(path: str, **params: str | int) -> dict:
    """GET a FRED endpoint as JSON. Spaced out to stay far below 120 requests per minute."""
    global last_headers
    time.sleep(0.6)
    try:
        response = client.get(
            path, params={**params, "api_key": API_KEY, "file_type": "json"}
        )
    except httpx.HTTPError as error:
        # httpx error messages include the URL, and the URL includes the key.
        sys.exit(f"{path}: request failed ({type(error).__name__})")
    if response.status_code != 200:
        sys.exit(
            f"{path}: HTTP {response.status_code}: {response.text.replace(API_KEY, '***')[:300]}"
        )
    last_headers = response.headers
    return response.json()


def table(headers: list[str], rows: list[list[object]]) -> None:
    print("| " + " | ".join(headers) + " |")
    print("|" + "---|" * len(headers))
    for row in rows:
        print("| " + " | ".join(str(cell) for cell in row) + " |")
    print()


print("# ALFRED spike (S4.1)\n")

print("## 1. Series metadata: `fred/series`\n")
series = fred("series", series_id="UNRATE")["seriess"][0]
table(
    ["Field", "Value"],
    [
        [key, series[key]]
        for key in (
            "title",
            "units",
            "frequency",
            "seasonal_adjustment",
            "observation_start",
            "last_updated",
            "realtime_start",
            "realtime_end",
        )
    ],
)
release = fred("series/release", series_id="UNRATE")["releases"][0]
print(f"Release: **{release['name']}** (release_id {release['id']}).\n")

print("## 2. Vintage dates: `fred/series/vintagedates`\n")
vintages = fred("series/vintagedates", series_id="UNRATE", **ALL_TIME)
dates: list[str] = vintages["vintage_dates"]
print(
    f"{vintages['count']} vintages, from {dates[0]} to {dates[-1]} (returned {len(dates)}, limit {vintages['limit']})."
)
early_1990 = [d for d in dates if "1990-01-15" <= d <= "1990-04-15"]
print(
    f"Vintages in early 1990: {', '.join(early_1990)}. Each is a date only, with no time of day.\n"
)

print("## 3. January 1990 across all real-time periods\n")
print(
    "`series/observations` with `realtime_start=1776-07-04&realtime_end=9999-12-31` returns every value the observation has had:\n"
)
history = fred(
    "series/observations",
    series_id="UNRATE",
    observation_start="1990-01-01",
    observation_end="1990-01-01",
    **ALL_TIME,
)
table(
    ["Value (%)", "realtime_start", "realtime_end"],
    [
        [o["value"], o["realtime_start"], o["realtime_end"]]
        for o in history["observations"]
    ],
)
first, latest = history["observations"][0], history["observations"][-1]
print(
    f"**First published:** {first['value']}% (vintage {first['realtime_start']}). **Current:** {latest['value']}% (since {latest['realtime_start']}).\n"
)

initial = fred(
    "series/observations",
    series_id="UNRATE",
    observation_start="1990-01-01",
    observation_end="1990-01-01",
    output_type=4,
    **ALL_TIME,
)
first_release = initial["observations"][0]
print(
    f"`output_type=4` (initial release only) agrees: {first_release['value']}% with realtime_start {first_release['realtime_start']}.\n"
)

print("## 4. As-of queries: what was known on June 4 vs. June 5, 2020\n")
print(
    "Setting `realtime_start` and `realtime_end` to one date returns the vintage in effect that day.\n"
)
rows = []
for as_of in ("2020-06-04", "2020-06-05", None):
    params = {"realtime_start": as_of, "realtime_end": as_of} if as_of else {}
    obs = fred(
        "series/observations",
        series_id="UNRATE",
        observation_start="2020-03-01",
        observation_end="2020-06-01",
        **params,
    )["observations"]
    values = {o["date"][:7]: o["value"] for o in obs}
    rows.append(
        [
            as_of or "today (default)",
            *(values.get(m, "—") for m in ("2020-03", "2020-04", "2020-05", "2020-06")),
        ]
    )
table(["Known as of", "Mar 2020", "Apr 2020", "May 2020", "Jun 2020"], rows)
release_dates = fred(
    "release/dates",
    release_id=release["id"],
    realtime_start="2020-05-01",
    realtime_end="2020-07-31",
    include_release_dates_with_no_data="true",
)
print(
    "Employment Situation release dates, May to July 2020 (`release/dates`): "
    + ", ".join(r["date"] for r in release_dates["release_dates"])
    + ". The API has no release *time*; 08:30 ET comes from BLS's schedule (S4.3).\n"
)

print("## 5. `output_type=2`: observations by vintage date (wide format)\n")
picked = [*early_1990[:3], dates[-1]]
wide = fred(
    "series/observations",
    series_id="UNRATE",
    observation_start="1989-12-01",
    observation_end="1990-03-01",
    output_type=2,
    vintage_dates=",".join(picked),
)
columns = [f"UNRATE_{d.replace('-', '')}" for d in picked]
table(
    ["date", *columns],
    [[o["date"], *(o.get(c, "—") for c in columns)] for o in wide["observations"]],
)
print(
    "In JSON, an observation that didn't exist yet in a vintage is simply left out of that "
    "row (shown here as —). It is not reported as `.`; that marker means a published value "
    "is missing (section 6).\n"
)

print("## 6. Missing-value marker\n")
gaps = fred(
    "series/observations",
    series_id="DGS10",
    observation_start="2019-12-30",
    observation_end="2020-01-03",
)
table(["DGS10 date", "value"], [[o["date"], o["value"]] for o in gaps["observations"]])
print(
    "Markets were closed on January 1, so the 10-year Treasury yield is `.`: a string, not a number or null.\n"
)

print("## 7. Request limits seen in this run\n")
rate_headers = {
    k: v for k, v in last_headers.items() if "rate" in k.lower() or "limit" in k.lower()
}
print(f"Rate-limit headers on the last response: {rate_headers or 'none'}.")
print(
    f"`limit` echoed by observations: {history['limit']}; by vintagedates: {vintages['limit']}."
)
print()

print("## 8. Terms check: the starter series\n")
print(
    "FRED's terms say series owned by third parties need the owner's permission for anything "
    'beyond personal use, and such series say "Copyright" in their notes.\n'
)
rows = []
for series_id in ("UNRATE", "PAYEMS", "CPIAUCSL", "GDP", "FEDFUNDS", "TB3MS"):
    info = fred("series", series_id=series_id)["seriess"][0]
    source = fred("series/release", series_id=series_id)["releases"][0]["name"]
    first_vintage = fred(
        "series/vintagedates", series_id=series_id, limit=1, **ALL_TIME
    )["vintage_dates"][0]
    copyrighted = "yes" if "copyright" in info.get("notes", "").lower() else "no"
    rows.append(
        [
            series_id,
            info["title"],
            source,
            info["observation_start"],
            first_vintage,
            copyrighted,
        ]
    )
table(
    [
        "Series",
        "Title",
        "Release",
        "Data starts",
        "First vintage",
        "Notes mention copyright",
    ],
    rows,
)
