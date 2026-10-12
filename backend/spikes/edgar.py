# /// script
# requires-python = ">=3.14"
# dependencies = ["httpx==0.28.1", "python-dotenv==1.2.3"]
#
# [tool.uv]
# exclude-newer = "2026-10-12T00:00:00Z"
# ///
"""Spike S5.1: EDGAR's timestamps, and which one means "available at".

Run from backend/:  uv run spikes/edgar.py
Needs SEC_USER_AGENT in backend/.env (a name plus a contact email; see .env.example).
Stays under SEC's limit of 10 requests per second. Prints Markdown; saves nothing.

Questions it answers, for Apple (CIK 320193):
- How acceptanceDateTime, filingDate, and reportDate differ, and how older filings are paginated.
- Whether acceptanceDateTime (which ends in "Z") is really UTC, checked two ways: against the
  "Accepted" time on filing index pages and SGML headers, and against the 5:30 PM ET
  filing-date cutoff. (It isn't: it runs ahead of the true time by the Eastern UTC offset.)
- That company facts keep every filed version of a value, while the frames API keeps only the last one.
"""

import os
import re
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
USER_AGENT = os.environ.get("SEC_USER_AGENT", "")
if "@" not in USER_AGENT:
    sys.exit(
        "Set SEC_USER_AGENT in backend/.env first: a name plus a contact email (see .env.example)."
    )

CIK = 320193
ET = ZoneInfo("America/New_York")
REVENUE = "RevenueFromContractWithCustomerExcludingAssessedTax"
client = httpx.Client(
    headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True
)


def get(url: str) -> httpx.Response:
    time.sleep(0.15)  # at most ~7 requests per second
    response = client.get(url)
    response.raise_for_status()
    return response


def table(headers: list[str], rows: list[list[object]]) -> None:
    print("| " + " | ".join(headers) + " |")
    print("|" + "---|" * len(headers))
    for row in rows:
        print("| " + " | ".join(str(cell) for cell in row) + " |")
    print()


def columns_to_rows(block: dict) -> list[dict]:
    return [
        dict(zip(block, values, strict=True))
        for values in zip(*block.values(), strict=True)
    ]


print("# EDGAR spike (S5.1)\n")

print("## 1. Submissions and pagination\n")
submissions = get(f"https://data.sec.gov/submissions/CIK{CIK:010d}.json").json()
filings = columns_to_rows(submissions["filings"]["recent"])
print(
    f"`{submissions['name']}`, tickers {submissions['tickers']}, fiscal year ends {submissions['fiscalYearEnd']} (MMDD)."
)
print(
    f"`filings.recent` holds {len(filings)} filings, from {filings[-1]['filingDate']} to {filings[0]['filingDate']}."
)
for page in submissions["filings"]["files"]:
    older = get(f"https://data.sec.gov/submissions/{page['name']}").json()
    filings.extend(columns_to_rows(older))
    print(
        f"Older page `{page['name']}`: {page['filingCount']} filings, {page['filingFrom']} to {page['filingTo']}."
    )
print(f"\nTotal: {len(filings)} filings. Fields per filing: {', '.join(filings[0])}.\n")

periodic = [f for f in filings if f["form"] in ("10-Q", "10-K", "10-Q/A", "10-K/A")]
print("## 2. The three dates on a periodic report\n")
table(
    [
        "form",
        "accession",
        "reportDate (period end)",
        "filingDate",
        "acceptanceDateTime (raw)",
    ],
    [
        [
            f["form"],
            f["accessionNumber"],
            f["reportDate"],
            f["filingDate"],
            f["acceptanceDateTime"],
        ]
        for f in periodic
        if "2019-09-01" <= f["reportDate"] <= "2020-10-01"
    ],
)


def json_instant(raw: str) -> datetime:
    """The submissions JSON's acceptanceDateTime, taken at face value (it ends in "Z")."""
    return datetime.fromisoformat(raw)


def corrected_utc(raw: str) -> datetime:
    """Subtract the Eastern UTC offset once more (4 hours in EDT, 5 in EST).

    EDGAR accepts filings only on weekdays, 6 AM to 10 PM ET, so the offset taken at the
    JSON time is the same as at the real time; DST switches happen at 2 AM on Sundays.
    """
    instant = json_instant(raw)
    return instant + instant.astimezone(ET).utcoffset()


print("## 3. Is acceptanceDateTime UTC? Check 1: EDGAR's own pages\n")
print(
    "Each filing's index page shows EDGAR's \"Accepted\" time, and its SGML header has "
    "ACCEPTANCE-DATETIME. Both are Eastern wall-clock time.\n"
)
by_period = {(f["form"], f["reportDate"]): f for f in periodic}
rows = []
for form, period in (
    ("10-Q", "2019-12-28"),
    ("10-Q", "2020-03-28"),
    ("10-K", "2020-09-26"),
):
    filing = by_period[(form, period)]
    accession = filing["accessionNumber"]
    folder = (
        f"https://www.sec.gov/Archives/edgar/data/{CIK}/{accession.replace('-', '')}"
    )
    index = get(f"{folder}/{accession}-index.htm").text
    match = re.search(r"Accepted</div>\s*<div class=\"info\">([^<]+)</div>", index)
    accepted = datetime.fromisoformat(match.group(1).strip()).replace(tzinfo=ET)
    header = get(f"{folder}/{accession}-index-headers.html").text
    sgml = re.search(r"ACCEPTANCE-DATETIME(?:&gt;|>)(\d{14})", header)
    gap = (json_instant(filing["acceptanceDateTime"]) - accepted).total_seconds() / 3600
    rows.append(
        [
            form,
            period,
            filing["acceptanceDateTime"],
            accepted.strftime("%Y-%m-%d %H:%M:%S %Z"),
            sgml.group(1) if sgml else "not found",
            f"{gap:+.0f} h",
            corrected_utc(filing["acceptanceDateTime"]).isoformat(),
            accepted.astimezone(UTC).isoformat(),
        ]
    )
table(
    [
        "form",
        "period",
        "JSON acceptanceDateTime",
        'Index page "Accepted"',
        "SGML ACCEPTANCE-DATETIME",
        "JSON minus true time",
        "JSON corrected (UTC)",
        "True time (UTC)",
    ],
    rows,
)
print(
    "The JSON is ahead of the real acceptance time by the Eastern UTC offset: 4 hours in "
    "summer (EDT), 5 in winter (EST). It isn't UTC, and it isn't Eastern time labeled Z.\n"
)

print("## 4. Is acceptanceDateTime UTC? Check 2: the 5:30 PM filing-date cutoff\n")
print(
    "Under Regulation S-T Rule 13, a filing accepted after 5:30 PM ET is dated the next "
    "business day (Forms 3, 4, and 5 get until 10 PM). Test three readings of the JSON "
    "against all of Apple's 10-K, 10-Q, and 8-K filings.\n"
)


def expected_filing_date(accepted_et: datetime) -> date:
    day = accepted_et.date()
    if (accepted_et.hour, accepted_et.minute, accepted_et.second) > (17, 30, 0):
        # Next business day. Federal holidays are ignored, so a few misses are expected.
        day += timedelta(days=1)
        while day.weekday() >= 5:
            day += timedelta(days=1)
    return day


def readings(raw: str) -> dict[str, datetime]:
    naive = datetime.fromisoformat(raw.removesuffix("Z").split(".")[0])
    return {
        "Eastern time labeled Z": naive.replace(tzinfo=ET),
        "true UTC": json_instant(raw).astimezone(ET),
        "UTC after subtracting the Eastern offset": corrected_utc(raw).astimezone(ET),
    }


tested = [
    f
    for f in filings
    if f["form"] in ("10-K", "10-Q", "8-K") and f["acceptanceDateTime"]
]
matches = dict.fromkeys(readings(tested[0]["acceptanceDateTime"]), 0)
misses = []
for filing in tested:
    for name, accepted_et in readings(filing["acceptanceDateTime"]).items():
        if expected_filing_date(accepted_et).isoformat() == filing["filingDate"]:
            matches[name] += 1
        elif name.startswith("UTC after"):
            misses.append(
                [
                    filing["form"],
                    filing["acceptanceDateTime"],
                    accepted_et,
                    filing["filingDate"],
                ]
            )
table(
    ["Reading of the timestamp", "filingDate explained"],
    [[name, f"{n} of {len(tested)}"] for name, n in matches.items()],
)
if misses:
    print("Filings the corrected reading doesn't explain:\n")
    table(
        ["form", "JSON acceptanceDateTime", "corrected, in Eastern time", "filingDate"],
        misses,
    )

print("## 5. Company facts keep every filed version\n")
facts = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK:010d}.json").json()
revenue = facts["facts"]["us-gaap"][REVENUE]["units"]["USD"]
quarter = [
    f for f in revenue if f.get("start") == "2019-12-29" and f["end"] == "2020-03-28"
]
accepted_at = {
    f["accessionNumber"]: corrected_utc(f["acceptanceDateTime"]).isoformat()
    for f in filings
    if f["acceptanceDateTime"]
}
table(
    [
        "val (USD)",
        "form",
        "fy",
        "fp",
        "filed",
        "accn",
        "frame",
        "accepted (corrected UTC)",
    ],
    [
        [
            f"{f['val']:,}",
            f["form"],
            f["fy"],
            f["fp"],
            f["filed"],
            f["accn"],
            f.get("frame", ""),
            accepted_at.get(f["accn"], "?"),
        ]
        for f in quarter
    ],
)
print(
    f"Revenue for the quarter ended March 28, 2020 (`{REVENUE}`) appears {len(quarter)} times: "
    "once in the original 10-Q and again in later filings. `filed` is a date only, so the "
    "acceptance time has to come from the submissions data (corrected as in section 3), "
    "joined on the accession number.\n"
)

print("## 6. The frames API keeps only the last-filed value\n")
frame = get(
    f"https://data.sec.gov/api/xbrl/frames/us-gaap/{REVENUE}/USD/CY2020Q1.json"
).json()
apple = next(row for row in frame["data"] if row["cik"] == CIK)
table(
    ["frame", "entity", "val (USD)", "accn", "start", "end"],
    [
        [
            frame["ccp"],
            apple["entityName"],
            f"{apple['val']:,}",
            apple["accn"],
            apple["start"],
            apple["end"],
        ]
    ],
)
original = min(quarter, key=lambda f: f["filed"])
print(
    f"The original 10-Q's accession is {original['accn']} (filed {original['filed']}); "
    f"the frame cites {apple['accn']}. "
    + (
        "They differ, so frames return the last-filed value, which isn't point-in-time."
        if apple["accn"] != original["accn"]
        else "They match for this period."
    )
)
