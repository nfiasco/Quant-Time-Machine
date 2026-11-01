"""What point-in-time reads return: one frozen dataclass per kind of record.

Field names match the API contract (doc/api-v1.md), so the /v1 endpoints (S8.2) can
return records as they are. Every record carries its provenance: when it became public
(`available_at`, in UTC), whether that time was assumed rather than published
(`time_assumed`, doc/time-model.md rule 11), and where it came from (`source` and
`source_ref`).
"""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class MacroObservation:
    """One observation of a macro series, as published by the knowledge time (S4.4)."""

    series_id: str
    title: str
    units: str
    frequency: str
    seasonal_adjustment: str
    release: str
    """The release it comes out in, such as "Employment Situation"."""
    period: date
    """The observation date: 2020-05-01 is May 2020."""
    value: float | None
    """None when the source published the observation as missing."""
    vintage_date: date
    """When this version was published (ALFRED's `realtime_start`)."""
    available_at: datetime
    time_assumed: bool
    source: str
    source_ref: str


@dataclass(frozen=True)
class PriceBar:
    """One raw daily bar, as known at the knowledge time (S6.3).

    Prices are as traded, never adjusted for later splits or dividends.
    """

    security_id: str
    ticker: str
    """The ticker at the knowledge time: FB for Facebook's bars in 2020."""
    cik: int | None
    session_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    available_at: datetime
    """The session's close."""
    time_assumed: bool
    source: str
    source_ref: str


@dataclass(frozen=True)
class Filing:
    """An SEC filing that EDGAR had accepted by the knowledge time (S5.4)."""

    security_id: str
    ticker: str
    """The ticker at the knowledge time."""
    cik: int
    """The filer: for Alphabet, Google Inc.'s CIK on filings before its 2015
    reorganization."""
    company_name: str
    """The company's name at the knowledge time."""
    accession_number: str
    form: str
    is_amendment: bool
    amends: str | None
    """The accession number of the filing an amendment changes, when it's known."""
    period_of_report: date | None
    filing_date: date
    """For display only: filings accepted after 5:30 PM ET get the next business day."""
    available_at: datetime
    """EDGAR's acceptance time, corrected (doc/time-model.md, rule 5)."""
    time_assumed: bool
    document_url: str | None
    index_url: str
    source: str
    source_ref: str


@dataclass(frozen=True)
class UniverseMember:
    """A security in a universe at the knowledge time (S6.5)."""

    universe: str
    security_id: str
    ticker: str | None
    """The ticker at the knowledge time, or None if the security had stopped trading
    but hadn't left the universe yet: Twitter from October 28 to November 1, 2022."""
    name: str
    """The name at the knowledge time."""
    cik: int | None
    added: date
    """The first day of this membership: the effective date of S&P's change, or
    2010-01-01 for a company already in the index then (D3)."""
    available_at: datetime
    """When the membership became known: 00:00 ET on `added`."""
    time_assumed: bool
    source: str
    source_ref: str
    """The announcement or filing that dates `added`."""


@dataclass(frozen=True)
class Security:
    """A security as identified at the knowledge time (S5.2)."""

    security_id: str
    """Ours, and stable: it doesn't change when the ticker, name, or CIK does."""
    ticker: str
    name: str
    """The name at the knowledge time, such as "Facebook, Inc." in 2020."""
    cik: int | None
    """SEC's ID for the company at the knowledge time, if it has one."""
    share_class: str | None
    effective_date: date | None
    """When this ticker, name, and CIK took effect; None if only SEC's file knows it."""
    available_at: datetime
    time_assumed: bool
    source: str
    source_ref: str
