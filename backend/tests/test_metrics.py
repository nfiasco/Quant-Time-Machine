from pathlib import Path

import pytest

from app.data.sources import xbrl
from app.data.sources.metrics import METRICS, all_concepts, load_metrics, metric

REVENUE = METRICS["revenue"]


def test_the_standard_metrics() -> None:
    assert {name: (m.unit, m.period, m.derive) for name, m in METRICS.items()} == {
        "revenue": ("USD", "duration", True),
        "net_income": ("USD", "duration", True),
        "eps_diluted": ("USD/shares", "duration", False),  # per-share amounts
        "operating_cash_flow": ("USD", "duration", True),
        "total_assets": ("USD", "instant", False),
        "shares_outstanding": ("shares", "instant", False),
    }


def test_revenue_tries_the_asc_606_names_first() -> None:
    assert REVENUE.concepts[:4] == (
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
        "us-gaap:Revenues",
        "us-gaap:SalesRevenueNet",
    )


def test_jpmorgan_has_its_own_revenue_concepts() -> None:
    assert REVENUE.concepts_for("jpmorgan") == (
        "us-gaap:RevenuesNetOfInterestExpense",
        "us-gaap:Revenues",
    )
    assert REVENUE.concepts_for("apple") == REVENUE.concepts
    assert REVENUE.overrides["jpmorgan"].source.startswith("https://www.sec.gov/")


def test_ingestion_keeps_every_concept_a_metric_lists() -> None:
    assert xbrl.CONCEPTS == all_concepts()
    assert "us-gaap:RevenuesNetOfInterestExpense" in xbrl.CONCEPTS


def test_an_unknown_metric_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown metric 'ebitda'"):
        metric("ebitda")


VALID = """
[[metrics]]
name = "revenue"
label = "revenue"
unit = "USD"
period = "duration"
derive = true
concepts = ["us-gaap:Revenues"]
"""


@pytest.mark.parametrize(
    ("text", "error"),
    [
        (VALID + VALID, "revenue is listed twice"),
        (VALID.replace('"revenue"\nlabel', '"Revenue"\nlabel'), "isn't a name"),
        (VALID.replace('label = "revenue"\n', ""), "needs a label"),
        (VALID.replace('"USD"', '"EUR"'), "unit must be one of"),
        (VALID.replace('"duration"', '"flow"'), "period must be duration or instant"),
        (VALID.replace('["us-gaap:Revenues"]', "[]"), "at least one concept"),
        (VALID.replace("us-gaap:Revenues", "Revenues"), "isn't a concept like"),
        (
            VALID.replace(
                '["us-gaap:Revenues"]', '["us-gaap:Revenues", "us-gaap:Revenues"]'
            ),
            "lists a concept twice",
        ),
        (
            VALID.replace('"duration"', '"instant"').replace("true", "false"),
            None,
        ),
        (VALID.replace('"duration"', '"instant"'), "can't be derived"),
        (
            VALID.replace('"duration"', '"instant"')
            .replace("true", "false")
            .replace(
                '["us-gaap:Revenues"]', '["us-gaap:Assets", "dei:EntityPublicFloat"]'
            ),
            "lists one concept",
        ),
    ],
)
def test_bad_metrics_are_refused(tmp_path: Path, text: str, error: str | None) -> None:
    path = tmp_path / "metrics.toml"
    path.write_text(text, encoding="utf-8")

    if error is None:
        assert list(load_metrics(path)) == ["revenue"]
    else:
        with pytest.raises(ValueError, match=error):
            load_metrics(path)


OVERRIDE = """
[[metrics.overrides]]
security = "jpmorgan"
concepts = ["us-gaap:RevenuesNetOfInterestExpense"]
reason = "Its filings say so."
source = "https://www.sec.gov/"
"""


@pytest.mark.parametrize(
    ("override", "error"),
    [
        (OVERRIDE, None),
        (OVERRIDE + OVERRIDE, "two overrides for jpmorgan"),
        (OVERRIDE.replace("jpmorgan", "lehman"), "'lehman' isn't in securities.toml"),
        (OVERRIDE.replace("Its filings say so.", " "), "needs a reason"),
        (OVERRIDE.replace("https://", "http://"), "needs a source"),
        (OVERRIDE.replace("us-gaap:RevenuesNet", "RevenuesNet"), "isn't a concept"),
    ],
)
def test_bad_overrides_are_refused(
    tmp_path: Path, override: str, error: str | None
) -> None:
    path = tmp_path / "metrics.toml"
    path.write_text(VALID + override, encoding="utf-8")

    if error is None:
        loaded = load_metrics(path)["revenue"]
        assert loaded.concepts_for("jpmorgan") == (
            "us-gaap:RevenuesNetOfInterestExpense",
        )
    else:
        with pytest.raises(ValueError, match=error):
            load_metrics(path)
