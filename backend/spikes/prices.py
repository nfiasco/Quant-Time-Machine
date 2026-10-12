# /// script
# requires-python = ">=3.14"
# dependencies = ["httpx==0.28.1", "python-dotenv==1.2.3"]
#
# [tool.uv]
# exclude-newer = "2026-10-12T00:00:00Z"
# ///
"""Spike S6.1: compare daily price sources on the data we actually need.

Run from backend/:  uv run spikes/prices.py
Optional keys in backend/.env: TIINGO_API_KEY, ALPHAVANTAGE_API_KEY (sources without a key are skipped).
Takes about two minutes because Alpha Vantage's free tier allows only a few requests per minute.
Prints Markdown; saves nothing.

For AAPL since 2005 and for delisted companies (Lehman Brothers: LEH, later LEHMQ; Twitter: TWTR) it checks:
- how far back history goes and whether delisted companies are covered,
- whether "close" is the raw price or already split-adjusted
  (AAPL closed at $702.10 on 2012-09-19; split-adjusted for 7:1 in 2014 and 4:1 in 2020 that's about $25.08),
- whether splits and dividends come with the data.

Every request identifies this script honestly. Sources that block automated clients are reported, never bypassed.
"""

import csv
import io
import os
import time
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
TIINGO_KEY = os.environ.get("TIINGO_API_KEY", "")
ALPHA_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "")

ET = ZoneInfo("America/New_York")
CHECK_DATE = "2012-09-19"
TICKERS = ("AAPL", "LEH", "LEHMQ", "TWTR")
USER_AGENT = "quant-time-machine-spike/0.1 (UD CISC 498 student project; price-source comparison)"
client = httpx.Client(
    headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True
)


@dataclass
class Pull:
    source: str
    ticker: str
    result: str = "ok"
    first: str = ""
    last: str = ""
    rows: int = 0
    close_on_check_date: str = ""
    splits: str = ""
    dividends: str = ""


pulls: list[Pull] = []
notes: dict[str, list[str]] = {}


def redact(text: str) -> str:
    for secret in (TIINGO_KEY, ALPHA_KEY):
        if secret:
            text = text.replace(secret, "***")
    return text


def summarize(
    pull: Pull,
    closes: dict[str, float],
    splits: list[str],
    dividends: list[tuple[str, float]],
) -> Pull:
    dates = sorted(closes)
    pull.rows = len(dates)
    if dates:
        pull.first, pull.last = dates[0], dates[-1]
    if CHECK_DATE in closes:
        value = closes[CHECK_DATE]
        kind = "raw" if value > 600 else "split-adjusted" if value < 30 else "?"
        pull.close_on_check_date = f"{value:.2f} ({kind})"
    pull.splits = ", ".join(splits) or "none"
    if dividends:
        first_date, first_amount = min(dividends)
        pull.dividends = f"{len(dividends)}; first {first_date} = {first_amount:g}"
    else:
        pull.dividends = "none"
    return pull


# --- Yahoo Finance: unofficial chart endpoint (the one yfinance wraps) ---------------------------
def yahoo(ticker: str) -> Pull:
    pull = Pull("Yahoo (unofficial)", ticker)
    params = {
        "period1": int(datetime(2005, 1, 1, tzinfo=UTC).timestamp()),
        "period2": int(datetime(2026, 1, 1, tzinfo=UTC).timestamp()),
        "interval": "1d",
        "events": "div,split",
        "includeAdjustedClose": "true",
    }
    response = client.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", params=params
    )
    try:
        chart = response.json()["chart"]
    except ValueError:
        pull.result = f"HTTP {response.status_code}, not JSON"
        return pull
    if chart.get("error") or not chart.get("result"):
        error = chart.get("error") or {}
        pull.result = (
            f"HTTP {response.status_code}: {error.get('description', 'no result')}"
        )
        return pull
    result = chart["result"][0]
    days = [
        datetime.fromtimestamp(t, ET).date().isoformat()
        for t in result.get("timestamp", [])
    ]
    raw_closes = result["indicators"]["quote"][0]["close"]
    closes = {d: c for d, c in zip(days, raw_closes, strict=True) if c is not None}
    events = result.get("events", {})
    splits = [
        f"{datetime.fromtimestamp(s['date'], ET).date()} {s['numerator']:g}:{s['denominator']:g}"
        for s in sorted(events.get("splits", {}).values(), key=lambda s: s["date"])
    ]
    dividends = [
        (datetime.fromtimestamp(d["date"], ET).date().isoformat(), d["amount"])
        for d in events.get("dividends", {}).values()
    ]
    return summarize(pull, closes, splits, dividends)


# --- Tiingo: official API, free tier with a key ----------------------------------------------------
def tiingo(ticker: str) -> Pull:
    pull = Pull("Tiingo", ticker)
    headers = {
        "Authorization": f"Token {TIINGO_KEY}",
        "Content-Type": "application/json",
    }
    meta = client.get(f"https://api.tiingo.com/tiingo/daily/{ticker}", headers=headers)
    if meta.status_code != 200:
        pull.result = f"metadata HTTP {meta.status_code}: {redact(meta.text)[:120]}"
        return pull
    info = meta.json()
    notes.setdefault("Tiingo", []).append(
        f"{ticker}: {info.get('name')} on {info.get('exchangeCode')}, listed {info.get('startDate')} to {info.get('endDate')}"
    )
    prices = client.get(
        f"https://api.tiingo.com/tiingo/daily/{ticker}/prices",
        headers=headers,
        params={"startDate": "2005-01-01", "endDate": "2025-12-31"},
    )
    if prices.status_code != 200:
        pull.result = f"prices HTTP {prices.status_code}: {redact(prices.text)[:120]}"
        return pull
    bars = prices.json()
    if not bars:
        pull.result = "listed, but no prices returned"
        return pull
    notes["Tiingo"].append(f"{ticker} fields: {', '.join(bars[0])}")
    closes = {b["date"][:10]: b["close"] for b in bars}
    splits = [
        f"{b['date'][:10]} {b['splitFactor']:g}:1"
        for b in bars
        if b.get("splitFactor", 1) != 1
    ]
    dividends = [(b["date"][:10], b["divCash"]) for b in bars if b.get("divCash")]
    return summarize(pull, closes, splits, dividends)


def tiingo_ticker_list() -> None:
    """Tiingo's published list of tickers, with the first and last date of data for each.

    A ticker whose data ends years ago (and isn't just renamed) is a delisted company Tiingo still covers.
    """
    response = client.get(
        "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"
    )
    if response.status_code != 200:
        notes.setdefault("Tiingo", []).append(
            f"supported_tickers.zip: HTTP {response.status_code}"
        )
        return
    with (
        zipfile.ZipFile(io.BytesIO(response.content)) as archive,
        archive.open(archive.namelist()[0]) as listing,
    ):
        rows = list(csv.DictReader(io.TextIOWrapper(listing, encoding="utf-8")))
    stocks = [r for r in rows if r.get("assetType") == "Stock" and r.get("endDate")]
    ended = [r for r in stocks if r["endDate"] < "2025-01-01"]
    notes.setdefault("Tiingo", []).append(
        f"supported_tickers.zip: {len(rows):,} rows; {len(stocks):,} stocks with dates, "
        f"{len(ended):,} of them ending before 2025 (delisted, merged, or renamed)"
    )
    by_year = Counter(r["endDate"][:4] for r in ended)
    spans = [("before 2005", "0000", "2004"), ("2005-2009", "2005", "2009")]
    spans += [("2010-2014", "2010", "2014"), ("2015-2019", "2015", "2019")]
    spans += [("2020-2024", "2020", "2024")]
    counts = [
        f"{label}: {sum(n for y, n in by_year.items() if lo <= y <= hi):,}"
        for label, lo, hi in spans
    ]
    notes["Tiingo"].append("stocks whose data ends, by year: " + "; ".join(counts))
    # Well-known companies that disappeared around the 2008 crisis (Bear Stearns, Countrywide,
    # Merrill Lynch, Wachovia). Tickers get reused, so check the end dates, not just presence.
    for row in rows:
        if row.get("ticker", "").upper() in (*TICKERS, "BSC", "CFC", "MER", "WB"):
            notes["Tiingo"].append(
                f"listed: {row['ticker']} on {row.get('exchange')} ({row.get('assetType')}), "
                f"{row.get('startDate') or '?'} to {row.get('endDate') or '?'}"
            )


# --- Alpha Vantage: official API, free tier with a key (25 requests per day) -----------------------
def alpha(**params: str) -> httpx.Response:
    time.sleep(13)  # stay under the free tier's per-minute limit
    return client.get(
        "https://www.alphavantage.co/query", params={**params, "apikey": ALPHA_KEY}
    )


def alpha_daily(ticker: str) -> Pull:
    pull = Pull("Alpha Vantage", ticker)
    for size in ("full", "compact"):
        body = alpha(
            function="TIME_SERIES_DAILY", symbol=ticker, outputsize=size
        ).json()
        series = body.get("Time Series (Daily)")
        if series:
            closes = {
                d: float(v["4. close"]) for d, v in series.items() if d >= "2005-01-01"
            }
            pull = summarize(pull, closes, [], [])
            pull.result = f"ok (outputsize={size})"
            pull.splits = pull.dividends = "not in this endpoint"
            return pull
        message = (
            body.get("Information")
            or body.get("Note")
            or body.get("Error Message")
            or str(body)[:120]
        )
        notes.setdefault("Alpha Vantage", []).append(
            f"TIME_SERIES_DAILY {ticker} outputsize={size}: {redact(message)}"
        )
    pull.result = "no data (see notes)"
    return pull


def alpha_extras() -> None:
    body = alpha(
        function="TIME_SERIES_DAILY_ADJUSTED", symbol="AAPL", outputsize="compact"
    ).json()
    message = body.get("Information") or body.get("Note") or body.get("Error Message")
    notes.setdefault("Alpha Vantage", []).append(
        f"TIME_SERIES_DAILY_ADJUSTED (splits and dividends): {redact(message) if message else 'available on this key'}"
    )
    listing = alpha(function="LISTING_STATUS", state="delisted")
    rows = list(csv.DictReader(io.StringIO(listing.text)))
    found = [
        f"{r['symbol']} ({r['name']}, delisted {r['delistingDate']})"
        for r in rows
        if r.get("symbol") in TICKERS
    ]
    notes["Alpha Vantage"].append(
        f"LISTING_STATUS state=delisted: {len(rows)} symbols; ours: {', '.join(found) or 'none'}"
    )


# --- Stooq: free CSV downloads, if they're reachable by a script ----------------------------------
def stooq() -> Pull:
    pull = Pull("Stooq", "AAPL")
    response = client.get("https://stooq.com/q/d/l/", params={"s": "aapl.us", "i": "d"})
    if (
        "verify your browser" in response.text.lower()
        or response.text.lstrip().startswith("<")
    ):
        pull.result = f"HTTP {response.status_code}: JavaScript browser check instead of CSV; not bypassed"
        return pull
    rows = list(csv.DictReader(io.StringIO(response.text)))
    closes = {r["Date"]: float(r["Close"]) for r in rows if r.get("Close")}
    return summarize(pull, closes, [], [])


for ticker in TICKERS:
    pulls.append(yahoo(ticker))
if TIINGO_KEY:
    for ticker in TICKERS:
        pulls.append(tiingo(ticker))
    tiingo_ticker_list()
else:
    notes["Tiingo"] = ["skipped: TIINGO_API_KEY not set"]
if ALPHA_KEY:
    for ticker in ("AAPL", "LEH", "TWTR"):
        pulls.append(alpha_daily(ticker))
    alpha_extras()
else:
    notes["Alpha Vantage"] = ["skipped: ALPHAVANTAGE_API_KEY not set"]
pulls.append(stooq())

print("# Price-source spike (S6.1)\n")
print(
    f"Requested range: 2005-01-01 to 2025-12-31. Check date for raw vs. adjusted: {CHECK_DATE}.\n"
)
headers = [
    "Source",
    "Ticker",
    "Result",
    "First",
    "Last",
    "Rows",
    f"Close {CHECK_DATE}",
    "Splits",
    "Dividends",
]
print("| " + " | ".join(headers) + " |")
print("|" + "---|" * len(headers))
for p in pulls:
    cells = [
        p.source,
        p.ticker,
        p.result,
        p.first,
        p.last,
        p.rows or "",
        p.close_on_check_date,
        p.splits if p.rows else "",
        p.dividends if p.rows else "",
    ]
    print("| " + " | ".join(str(c) for c in cells) + " |")
print()
for source, lines in notes.items():
    print(f"**{source} notes**\n")
    for line in lines:
        print(f"- {line}")
    print()
