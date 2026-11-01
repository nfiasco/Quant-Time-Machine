"""Every table in the point-in-time store, by name.

Each ingestion task defines its table here (S4.2, S5.3, S5.5, S6.2), so that every
reader sees the same list no matter which modules were imported first.
`PointInTimeView` reads the tables listed in TABLES, and the test fixture loader matches
each tests/fixtures/<table>.csv to one of them, so a new table needs a fixture file too.
"""

from app.data.store import TableSpec

MACRO_OBSERVATIONS = TableSpec(
    name="macro_observations",
    key=("series_id", "observation_date"),
    columns={
        "series_id": "VARCHAR",
        "observation_date": "DATE",
        "value": "DOUBLE",
        "vintage_date": "DATE",
    },
)
"""Every published version of each macro observation, from ALFRED (S4.2).

A version is the value from one vintage: `vintage_date` is ALFRED's `realtime_start`,
and `available_at` is that date at the release's time in New York (S4.3), or the end of
the day, flagged `time_assumed`, when the time isn't known. `value` is None when the
source published the observation as missing (FRED's ".")."""

SECURITIES = TableSpec(
    name="securities",
    key=("security_id",),
    columns={
        "security_id": "VARCHAR",
        "ticker": "VARCHAR",
        "name": "VARCHAR",
        "cik": "BIGINT",
        "share_class": "VARCHAR",
        "effective_date": "DATE",
    },
)
"""Each curated security's ticker, name, and CIK over time (S5.2).

A row is a change that took effect on `effective_date`, known from 00:00 ET that day, so
a security's latest version at a knowledge time is what applied then. `ticker` is None
once the security was delisted."""

SEC_TICKERS = TableSpec(
    name="sec_tickers",
    key=("cik", "ticker"),
    columns={"cik": "BIGINT", "ticker": "VARCHAR", "name": "VARCHAR"},
)
"""Snapshots of SEC's ticker file, which lists only the tickers in use when it's
downloaded (S5.2). Every row of a snapshot has that download's time as `available_at`,
flagged `time_assumed`."""

PRICE_BARS = TableSpec(
    name="price_bars",
    key=("security_id", "session_date"),
    columns={
        "security_id": "VARCHAR",
        "session_date": "DATE",
        "open": "DOUBLE",
        "high": "DOUBLE",
        "low": "DOUBLE",
        "close": "DOUBLE",
        "volume": "BIGINT",
    },
)
"""Raw daily bars, as traded and never adjusted for later splits or dividends (S6.2).

A bar is known at its session's close: 16:00 ET, or 13:00 ET on early-close days
(doc/time-model.md, rule 4)."""

CORPORATE_ACTIONS = TableSpec(
    name="corporate_actions",
    key=("security_id", "ex_date", "action"),
    columns={
        "security_id": "VARCHAR",
        "ex_date": "DATE",
        "action": "VARCHAR",
        "value": "DOUBLE",
    },
)
"""Splits and cash dividends by ex-date, from the same bars (S6.2).

`action` is "split", where `value` is the vendor's split factor as given (new shares
per old share, such as 7.000007 for Apple's 7-for-1 in 2014; S6.4 rounds it), or
"dividend", where `value` is the cash paid per share. Each is part of its ex-date's
bar, so it's known at that session's close."""

FILINGS = TableSpec(
    name="filings",
    key=("cik", "accession_number"),
    columns={
        "cik": "BIGINT",
        "accession_number": "VARCHAR",
        "form": "VARCHAR",
        "filing_date": "DATE",
        "period_of_report": "DATE",
        "is_amendment": "BOOLEAN",
        "amends": "VARCHAR",
        "primary_document": "VARCHAR",
        "items": "VARCHAR",
        "acceptance_raw": "VARCHAR",
    },
)
"""Each company's 10-K, 10-Q, and 8-K filings and their amendments, from EDGAR (S5.3).

`available_at` is the filing's acceptance time, corrected (doc/time-model.md, rule 5),
never its filing date. `acceptance_raw` keeps EDGAR's uncorrected value for auditing.
`amends` is the accession number of the filing an amendment changes, when it's known."""

XBRL_FACTS = TableSpec(
    name="xbrl_facts",
    key=(
        "cik",
        "accession_number",
        "concept",
        "unit",
        "period_end",
        "duration_days",
        "value",
    ),
    columns={
        "cik": "BIGINT",
        "accession_number": "VARCHAR",
        "concept": "VARCHAR",
        "unit": "VARCHAR",
        "period_start": "DATE",
        "period_end": "DATE",
        "duration_days": "BIGINT",
        "value": "DOUBLE",
        "fiscal_year": "BIGINT",
        "fiscal_period": "VARCHAR",
        "form": "VARCHAR",
        "filed": "DATE",
    },
)
"""Each value a company reported for a curated XBRL concept, from EDGAR (S5.5).

A row is one fact as one filing reported it. A value repeated in a later filing, as a
comparative or a restatement, is another row, known from that filing's acceptance time
(doc/time-model.md, rule 6). `available_at` is the acceptance time of the filing
`accession_number` names, from `filings`; for a filing that isn't there, such as a
proxy statement, it's the end of `filed` in New York, flagged `time_assumed` (rule 11).

`concept` carries its taxonomy, as in "us-gaap:Revenues". `period_start` is None for an
instant, such as total assets on a balance-sheet date. `duration_days` counts the
period's days, both ends included: 91 for a 13-week quarter, 0 for an instant. It's in
the key because `period_start` can't be, and `value` is too, so only exact duplicates
collapse. `fiscal_year` and `fiscal_period` are the filing's, as SEC gives them, so a
comparative carries the later filing's. SEC's `frame` is never stored: it marks the
last-filed fact for each period, which no one knew at the time."""

UNIVERSE_MEMBERS = TableSpec(
    name="universe_members",
    key=("universe", "security_id", "added"),
    columns={
        "universe": "VARCHAR",
        "security_id": "VARCHAR",
        "added": "DATE",
        "removed": "DATE",
    },
)
"""Each curated universe's membership spells, from sources/universes.toml (S6.5, D3).

A spell is a security's time in a universe, from `added` until `removed`. Its first
version is known from 00:00 ET on `added`, with `removed` None. If the security leaves,
a second version, known from 00:00 ET on `removed`, sets it. So no row shows a removal
before it happened (doc/time-model.md, rule 8), and a spell's latest version known at a
knowledge time says whether the security was a member then."""

TABLES: dict[str, TableSpec] = {
    spec.name: spec
    for spec in (
        MACRO_OBSERVATIONS,
        SECURITIES,
        SEC_TICKERS,
        PRICE_BARS,
        CORPORATE_ACTIONS,
        FILINGS,
        XBRL_FACTS,
        UNIVERSE_MEMBERS,
    )
}
