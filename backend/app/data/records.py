"""What point-in-time reads return: one frozen dataclass per kind of record.

Field names match the API contract (doc/reference/api-v1.md), so the /v1 endpoints (S8.2) can
return records as they are. Every record carries its provenance: when it became public
(`available_at`, in UTC), whether that time was assumed rather than published
(`time_assumed`, doc/reference/time-model.md rule 11), and where it came from (`source` and
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
    ticker: str | None
    """The ticker at the knowledge time: FB for Facebook's bars in 2020. None for the
    bars of a security that had stopped trading, read by its ID (S7.3)."""
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
class CorporateAction:
    """A split or a cash dividend, as known at the knowledge time (S6.4).

    Each came with its ex-date's bar, so it's known at that session's close.
    """

    security_id: str
    ticker: str | None
    """The ticker at the knowledge time, or None once the security had stopped
    trading, as for `PriceBar`."""
    cik: int | None
    ex_date: date
    action: str
    """"split" or "dividend"."""
    value: float
    """For a split, the vendor's factor as given: new shares per old share, such as
    7.000007 for Apple's 7-for-1 in 2014, which total returns round
    (app/backtest/returns.py). For a dividend, the cash paid per share."""
    available_at: datetime
    """The ex-date's close."""
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
    """EDGAR's acceptance time, corrected (doc/reference/time-model.md, rule 5)."""
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
class UniverseChange:
    """A security joining or leaving a universe, read by the look-ahead module
    (app/data/look_ahead.py) because it took effect after the knowledge time (S8.3)."""

    universe: str
    security_id: str
    change: str
    """"joins" or "leaves"."""
    effective: date
    """The first day of the change: the day it joined, or the first day it wasn't a
    member any more."""
    available_at: datetime
    """00:00 ET on `effective`: a change applies from its effective date, never
    earlier (doc/reference/time-model.md, rule 8)."""
    time_assumed: bool
    source: str
    source_ref: str
    """The announcement or filing that dates it."""


@dataclass(frozen=True)
class NextBar:
    """When a security's next daily bar became known, read by the look-ahead module
    (S8.3). It carries no prices: they weren't known at the knowledge time."""

    session_date: date
    available_at: datetime
    """The session's close."""


@dataclass(frozen=True)
class Security:
    """A security as identified at the knowledge time (S5.2)."""

    security_id: str
    """Ours, and stable: it doesn't change when the ticker, name, or CIK does."""
    ticker: str | None
    """The ticker at the knowledge time, or None once the security had stopped
    trading: Twitter's from October 28, 2022. Only `PointInTimeView.get_security`
    finds such a security; `resolve_ticker` always finds one with its ticker."""
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


@dataclass(frozen=True)
class ConceptUse:
    """How many of a company's filings reported a metric through one concept (S5.6)."""

    concept: str
    filings: int
    first_period: date
    """The earliest period of report among them."""
    last_period: date


@dataclass(frozen=True)
class FundamentalsCoverage:
    """How well a standard metric covers one company's 10-Qs and 10-Ks (S5.6).

    Its original 10-Qs and 10-Ks are checked from its first XBRL fact on, when tagging
    began for it, through the knowledge time.
    """

    security_id: str
    name: str
    """The company's name at the knowledge time."""
    metric: str
    concepts: tuple[str, ...]
    """The concepts tried for it, most preferred first."""
    filings_checked: int
    concepts_used: tuple[ConceptUse, ...]
    """In the order tried."""
    missing: tuple[date, ...]
    """Periods of report whose filing reported none of the concepts for that period."""
    ambiguous: tuple[date, ...]
    """Periods of report whose filing reported two values for the same period."""


@dataclass(frozen=True)
class DateRange:
    """The first and last dates of something in our data, both included."""

    first: date
    last: date


@dataclass(frozen=True)
class SeriesCoverage:
    """A series in the macro catalog, and how much of it was published by the knowledge
    time (S8.5)."""

    series_id: str
    title: str
    units: str
    frequency: str
    seasonal_adjustment: str
    release: str
    observations: DateRange | None
    """The first and last observation dates published by then; None if none was."""
    vintages: DateRange | None
    """The dates of the first and last vintages published by then. ALFRED's archive
    starts later than the data for every starter series, so an observation is unknown
    until the first vintage that has it."""


@dataclass(frozen=True)
class CompanyCoverage:
    """A universe's member at the knowledge time, and how far its data reaches by then
    (S8.5)."""

    universe: str
    security_id: str
    ticker: str | None
    """The ticker at the knowledge time, or None if the security had stopped trading
    but hadn't left the universe yet."""
    name: str
    """The name at the knowledge time."""
    cik: int | None
    added: date
    """The first day of its membership."""
    prices: DateRange | None
    """The sessions of its first and last daily bars known then."""
    filings: DateRange | None
    """The New York dates on which EDGAR accepted its first and last 10-K, 10-Q, or
    8-K, or an amendment, known then, across every CIK it had."""
    fundamentals: DateRange | None
    """The New York dates on which EDGAR accepted the first and last filings whose
    XBRL facts we have, known then."""


@dataclass(frozen=True)
class Fundamental:
    """One quarter of a standard metric, as known at the knowledge time (S5.7).

    For an instant metric, such as total assets, it's the value on one date.
    """

    security_id: str
    ticker: str
    """The ticker at the knowledge time."""
    cik: int | None
    """The security's CIK at the knowledge time."""
    metric: str
    """A metric in app/data/sources/metrics.toml, such as "revenue"."""
    concept: str
    """The XBRL concept the value came from, such as
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"."""
    unit: str
    period_start: date | None
    """None for an instant."""
    period_end: date
    fiscal_year: int | None
    fiscal_period: str | None
    """"Q1" to "Q4", from the filing that reported the period as its own; None if no
    filing in our data did."""
    value: float
    derived: bool
    """True for a quarter computed from two year-to-date totals, such as a fourth
    quarter from the full year minus the first nine months."""
    accession_numbers: tuple[str, ...]
    """The filings the value came from: one, or two for a derived quarter, the longer
    total's first."""
    available_at: datetime
    """When the last of those filings was accepted (doc/reference/time-model.md, rule 6)."""
    time_assumed: bool
    source: str
    source_ref: str
    """The accession number, or "<longer total's> minus <shorter total's>"."""
