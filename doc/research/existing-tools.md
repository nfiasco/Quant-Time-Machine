# How existing tools answer the canonical question

> **Story S2.2.** Tools compared on 2026-11-16. The hands-on runs used the raw downloads already in `DATA_DIR/raw` (Tiingo prices and SEC company facts, fetched 2026-10-31 to 2026-11-01) and were checked against the [canonical run](canonical-backtest.md) on data version 20261111T030742Z. Vendor facts come from each vendor's own pages, retrieved the same day; plans and terms change, so re-check them before quoting.

**The question.** [The canonical question](canonical-backtest.md): from 2010 to 2025, would buying large US companies whose revenue growth was improving, and whose shares had been rising, have beaten the market, using only what was known at each decision?

**The short answer.** Every tool we looked at can run it, but none of them knows when a number became public unless you build that yourself, and a mistake doesn't show. Written the obvious way in a notebook, the backtest returns 25.1% a year. Written carefully, it returns 18.5%, the same as our engine. Nothing in the first version warns that it is 6.6 points a year too good.

## The options

Four options, plus Quant Time Machine for comparison. Two were tried hands-on ([below](#tried-hands-on)); QuantConnect needs an account, and the UD library denied our request for WRDS, so those two are compared from their documentation.

| | A notebook (pandas) with free downloads | An open-source backtester (backtrader) | QuantConnect (LEAN, cloud) | WRDS (CRSP and Compustat) | Quant Time Machine |
| --- | --- | --- | --- | --- | --- |
| **Tried** | ✓ [`notebook.py`](../../backend/spikes/tool_compare/notebook.py) | ✓ [`backtrader_try.py`](../../backend/spikes/tool_compare/backtrader_try.py) | From its docs | From its docs; access denied | [The canonical run](canonical-backtest.md) |
| **Setup effort** | Download prices (Tiingo key) and SEC's company facts, then write about 300 lines: concept choice, quarter derivation, dating, membership, momentum, the backtest | The notebook's data and signal code, plus about 100 lines of backtrader: one feed per company, a strategy, and three workarounds ([below](#backtrader)) | A browser account; algorithms in Python or C# on QuantConnect's data | A university subscription and an account; then the same signal code as a notebook, in SQL or Python | One spec: `uv run python -m app.runs canonical.json`, or `POST /v1/backtests`. The builder's run button is still S9.5's |
| **Cost** | Free (Tiingo's free plan is internal use only; SEC is free) | Free, open source (last release 1.9.78.123, April 2023) | Free plan with corporate fundamentals and daily data; paid plans from $84 a month ([pricing](https://www.quantconnect.com/pricing)) | Institutional subscription; free to Lerner College users at UD, but **denied to this project** | Free data; $5 a month of hosting (D4) |
| **Coverage** | Tiingo prices from 1980 with partial delisted coverage; XBRL revenue from 2009–2011 | Whatever you load | Morningstar fundamentals for about 8,000 US equities from January 1998, delisted companies included ([dataset docs](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/morningstar/us-fundamental-data)) | CRSP: every US listing with delisting returns; Compustat: fundamentals for decades | Universe v1: 50 curated companies, 2010–2025; six macro series with vintages |
| **When data became public** | Not tracked. SEC gives a filing date per value; the rest is up to you | Not tracked. backtrader has no fundamentals and no notion of when a fact became known | Partly. Since a 2026 data migration, statements are dated by filing, a median of 63 days later than before; before 2013 the new feeds lack filing dates and use a nominal 45-day delay ([announcement](https://www.quantconnect.com/announcements/21449/migrating-to-morningstar-039-s-new-equity-data-feeds/)) | Available, but separate. Compustat Snapshot keeps values as they stood at each point in time, from 1986 ([UNC guide](https://kenanflaglerresearchtools.web.unc.edu/research-resource/compustat-snapshot/)); the standard files are revised over time | Every row: `available_at` to the microsecond, enforced by `PointInTimeView` and checked by the audit |
| **Reproducibility** | Only if you save the downloads; a re-download gets today's restated data | Deterministic for fixed inputs; same caveat for the data | Tied to the vendor's current data: the 2026 migration moved dates, so an older backtest of those fields wouldn't reproduce | Fixed vintages are possible but manual | A run ID hashes the spec, the data version, and the engine; a re-run gives byte-identical files |
| **Public display** | Tiingo: not without permission. SEC: yes | Same as the data | QuantConnect's terms govern its data | No: internal academic use only | SEC and FRED data yes; raw Tiingo prices off the public API (D2) |

Not tried: [Zipline-reloaded](https://github.com/stefan-jansen/zipline-reloaded) and [vectorbt](https://github.com/polakowo/vectorbt). Like backtrader, neither comes with point-in-time fundamentals; they would need the notebook's signal code too.

## Tried hands-on

Both attempts read the same raw files our ingestion downloaded, so the inputs are identical to the engine's. Neither needs a key or the network.

```bash
cd backend
uv run spikes/tool_compare/notebook.py --compare-run data/runs/<canonical run ID>
uv run spikes/tool_compare/backtrader_try.py
```

Each follows the canonical spec's other rules: a decision on each month's first trading day, filled at that day's close, 12-1 momentum, revenue growth acceleration above zero, equal weights, long only, and 10 bps of the value traded. Writing time wasn't measured; code size, run time, and the decisions each tool leaves to the researcher stand in for effort.

### A notebook

The notebook, [`notebook.py`](../../backend/spikes/tool_compare/notebook.py), is about 300 lines of pandas. It runs four versions, which differ in only two things: how a quarter's revenue is dated, and which companies count.

- **Dating "period end"** is what most notebooks do first. It takes SEC's company facts as they are today, restatements included, and counts each quarter from the day it ended, weeks before its 10-Q was filed.
- **Dating "filed"** counts each value from the day after its filing, a restatement only from its own filing, and a derived fourth quarter only once both of its filings are out.
- **"Today's members"** uses all 50 companies for all 16 years. **"Members at the time"** uses each only while it was in the universe.

| Version | Growth of $1 | CAGR | Holdings, mean | Same holdings as the engine | Overlap with the engine, mean |
| --- | --- | --- | --- | --- | --- |
| Naive: period-end dating, today's members | $35.99 | 25.1% | 15.2 | 2 of 192 decisions | 51% |
| Period-end dating, members at the time | $24.49 | 22.2% | 13.9 | 6 of 192 | 55% |
| Filing dates, today's members | $20.93 | 21.0% | 14.8 | 21 of 192 | 82% |
| **Careful: filing dates, members at the time** | **$15.15** | **18.5%** | 13.5 | 36 of 192 | 89% |
| The engine ([canonical run](canonical-backtest.md)) | $15.04 | 18.5% | 14.9 | | |
| SPY, held | $8.03 | 13.9% | | | |

"Overlap" is the share of stocks the two portfolios have in common at a decision (Jaccard), averaged over 192 decisions. The whole script runs in about a minute; each version takes 5 to 25 seconds.

- **Look-ahead adds 6.6 points a year, silently.** Dating revenue by its quarter's end, with today's restated values, adds 3.7 points on its own; using today's member list adds 2.5 on its own; together they add 6.6. None of the versions raises an error or a warning.
- **The careful notebook matches the engine's return, but not its portfolios.** It holds exactly the engine's stocks at only 36 of 192 decisions. It misses most often where the engine has a rule the notebook doesn't: Coca-Cola and Johnson & Johnson tagged revenue `SalesRevenueGoodsNet` until 2018, and lenders such as Wells Fargo and Discover report it differently ([`metrics.toml`](../../backend/app/data/sources/metrics.toml) lists the overrides); Alphabet's facts sit under Google's CIK until 2015; and PepsiCo's 12-, 12-, 12-, and 16-week quarters break a nine-month window of 260 to 285 days. The matching CAGR is partly luck.
- **What the researcher had to decide:** which revenue concepts count and in what order, how to derive a fourth quarter, what "a year earlier" means for 52- and 53-week years, how stale a quarter may be, that a filing date without a time is known only the next day, how to read several Tiingo fetches of one ticker, what to do with a company that stops trading, and how to charge costs. Each is a line or two; each is easy to get wrong without noticing.

### backtrader

[`backtrader_try.py`](../../backend/spikes/tool_compare/backtrader_try.py) takes the careful notebook's holdings and lets backtrader do the trading: about 100 lines on top of the notebook's signal code.

| Attempt | Growth of $1 | CAGR | Orders rejected |
| --- | --- | --- | --- |
| First: feeds as downloaded, sells and buys in name order | $12.34 | 17.0% | 190 |
| Final: padded feeds, sells before buys, 0.5% cash kept back | $14.99 | 18.5% | 0 |

The first attempt ran without an error and was 1.5 points a year low. Three backtrader behaviors caused it, each needing a workaround:

1. **Late listings hold everything back.** backtrader calls a strategy only once every feed has a bar, so AbbVie (2013), PayPal (2015), or Airbnb (2020) would delay the whole backtest. The strategy has to trade from `prenext` too.
2. **A feed that ends can't fill an order.** Celgene and Xilinx stopped trading when they were acquired, so their positions could never be sold and sat in the portfolio at their last close. The fix pads each feed with its last close until the end.
3. **Orders are rejected for "Margin" in a quiet way.** Orders fill in the order they're placed, so a purchase placed before a sale can find no cash: 190 orders were rejected, and their cash sat idle. In October 2022, for example, the strategy meant to hold four stocks and ExxonMobil was never bought. The fix places every sale before any purchase and keeps 0.5% back for commissions; with 0.1% kept back, 33 orders are still rejected.

backtrader then agrees with the notebook to within its whole-share rounding and the cash it keeps back. It took about 10 seconds to run, and its last release prints `SyntaxWarning`s on Python 3.14.

## Takeaways for our positioning

1. **The hard part of a point-in-time backtest is the dates, and every tool leaves them to you.** The two tools we tried run the canonical question in under a minute. Neither knows when a number became public, so an honest result depends on a few hundred lines of the researcher's own date handling, and the obvious version overstates the return by 6.6 points a year without a warning. Quant Time Machine's pitch is that this layer is built, tested, and the same for everyone.
2. **The data that solves it is paid, partial, or private.** WRDS has first-reported fundamentals and delisting returns, but it's an institutional subscription, internal-use only, and was denied to us. QuantConnect dates fundamentals by filing, but only approximately before 2013, and it changed those dates in 2026. We build from free primary sources (SEC filings with acceptance times, ALFRED vintages) that anyone can check and display.
3. **A matching number isn't an audit.** The careful notebook got the engine's 18.5%, but held different stocks at 156 of 192 decisions, and nothing told it why. What we offer beyond a correct number is the evidence: each decision's inputs and their timestamps, warnings for every missing value, and a run ID that reproduces the files byte for byte.

These feed the success measures in the [evaluation plan](evaluation-plan.md), which uses this page as its research-effort baseline.
