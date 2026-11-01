"""Standard metrics: what "revenue" and the rest mean, as XBRL concepts (S5.6).

The curated file metrics.toml lists, for each metric, the concepts that can report it,
most preferred first, and overrides for securities whose filings need another list.
`ingest sec` keeps every concept listed (sources/xbrl.py). app/data/fundamentals.py
resolves them: for every period, the first concept with a value supplies it, and the
value carries its concept.
"""

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from app.data.sources.securities import CURATED, Curated

METRICS_FILE = Path(__file__).with_name("metrics.toml")

UNITS = frozenset({"USD", "USD/shares", "shares"})
"""The units the metrics are filed in."""

Period = Literal["duration", "instant"]

_NAME = re.compile(r"[a-z][a-z0-9_]*", re.ASCII)
_CONCEPT = re.compile(r"(us-gaap|dei):[A-Z][A-Za-z0-9]*", re.ASCII)


@dataclass(frozen=True)
class Override:
    """Another list of concepts for one security, and why."""

    concepts: tuple[str, ...]
    reason: str
    source: str
    """A filing or page that shows the reason."""


@dataclass(frozen=True)
class Metric:
    """A standard metric and the XBRL concepts that can report it."""

    name: str
    label: str
    """How a sentence names it: "revenue", "diluted EPS"."""
    unit: str
    period: Period
    """"duration" for an amount over a period, "instant" for a balance on a date."""
    derive: bool
    """Whether a quarter can be computed from year-to-date totals (S5.7)."""
    concepts: tuple[str, ...]
    """Most preferred first, each with its taxonomy, such as "us-gaap:Revenues"."""
    overrides: Mapping[str, Override]
    """By security ID."""

    def concepts_for(self, security_id: str) -> tuple[str, ...]:
        """The concepts to try for a security, most preferred first."""
        override = self.overrides.get(security_id)
        return self.concepts if override is None else override.concepts


def load_metrics(
    path: Path = METRICS_FILE, curated: Curated = CURATED
) -> dict[str, Metric]:
    """Read and check the curated metrics, by name.

    Raises ValueError for a name used twice, an unknown unit or period, a concept that
    isn't written like "us-gaap:Revenues", an empty or repeated concept, an instant
    metric with more than one concept or set to derive quarters, or an override for a
    security that isn't in securities.toml, or without a reason or https source.
    """
    with path.open("rb") as file:
        config = tomllib.load(file)
    metrics: dict[str, Metric] = {}
    for entry in config.get("metrics", ()):
        metric = _metric(entry, path.name, curated)
        if metric.name in metrics:
            raise ValueError(f"{path.name}: {metric.name} is listed twice")
        metrics[metric.name] = metric
    return metrics


def _metric(entry: Mapping[str, Any], file: str, curated: Curated) -> Metric:
    name = entry.get("name", "")
    if not _NAME.fullmatch(name):
        raise ValueError(f"{file}: {name!r} isn't a name like net_income")
    where = f"{file}: {name}"
    if not entry.get("label"):
        raise ValueError(f"{where} needs a label")
    if entry.get("unit") not in UNITS:
        raise ValueError(f"{where}: unit must be one of {sorted(UNITS)}")
    period = entry.get("period")
    if period not in get_args(Period):
        raise ValueError(f"{where}: period must be duration or instant")
    derive = entry.get("derive", False)
    if type(derive) is not bool:
        raise ValueError(f"{where}: derive must be true or false")
    if derive and period == "instant":
        raise ValueError(f"{where}: quarters of an instant can't be derived")
    concepts = _concepts(entry.get("concepts"), period, where)

    overrides: dict[str, Override] = {}
    for item in entry.get("overrides", ()):
        security = item.get("security", "")
        if security not in curated.securities:
            raise ValueError(f"{where}: {security!r} isn't in securities.toml")
        if security in overrides:
            raise ValueError(f"{where}: two overrides for {security}")
        if not str(item.get("reason", "")).strip():
            raise ValueError(f"{where}: the override for {security} needs a reason")
        if not str(item.get("source", "")).startswith("https://"):
            raise ValueError(f"{where}: the override for {security} needs a source")
        overrides[security] = Override(
            concepts=_concepts(item.get("concepts"), period, f"{where}, {security}"),
            reason=" ".join(item["reason"].split()),
            source=item["source"],
        )
    return Metric(
        name=name,
        label=entry["label"],
        unit=entry["unit"],
        period=period,
        derive=derive,
        concepts=concepts,
        overrides=overrides,
    )


def _concepts(items: Any, period: str, where: str) -> tuple[str, ...]:
    if not isinstance(items, list) or not items:
        raise ValueError(f"{where}: concepts must be a list of at least one concept")
    for concept in items:
        if not isinstance(concept, str) or not _CONCEPT.fullmatch(concept):
            raise ValueError(
                f"{where}: {concept!r} isn't a concept like us-gaap:Revenues"
            )
    if len(set(items)) < len(items):
        raise ValueError(f"{where} lists a concept twice")
    if period == "instant" and len(items) > 1:
        raise ValueError(
            f"{where}: an instant metric lists one concept, because two concepts can "
            "be measured on different dates"
        )
    return tuple(items)


METRICS = load_metrics()
"""The standard metrics, by name."""


def all_concepts(metrics: Mapping[str, Metric] = METRICS) -> frozenset[str]:
    """Every concept a metric or override lists: the ones ingestion keeps."""
    return frozenset(
        concept
        for metric in metrics.values()
        for concepts in (
            metric.concepts,
            *(o.concepts for o in metric.overrides.values()),
        )
        for concept in concepts
    )


def metric(name: str, metrics: Mapping[str, Metric] = METRICS) -> Metric:
    """A metric by name. Raises ValueError for an unknown one."""
    found = metrics.get(name)
    if found is None:
        raise ValueError(
            f"unknown metric {name!r}; expected one of {', '.join(metrics)}"
        )
    return found
