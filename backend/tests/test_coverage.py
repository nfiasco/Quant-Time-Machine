from pathlib import Path

import pytest

from app.config import Settings
from app.data import coverage
from app.data.sources.metrics import METRICS
from tests.fixture_loader import FIXTURE_DATA_VERSION


@pytest.fixture
def use_fixture_store(monkeypatch: pytest.MonkeyPatch, fixture_store: Path) -> None:
    """Make the command read the fixture store instead of backend/.env's DATA_DIR."""
    settings = Settings(_env_file=None, data_dir=fixture_store.parent)
    monkeypatch.setattr(coverage, "get_settings", lambda: settings)


@pytest.mark.usefixtures("use_fixture_store")
def test_the_report_has_every_metric_for_every_member(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert coverage.main(["--as-of", "2021-06-01"]) == 0

    out = capsys.readouterr().out
    assert out.startswith(
        "# Coverage\n\n`starter_large_caps` as known at June 1, 2021, 9:30 AM ET, "
        f"data version {FIXTURE_DATA_VERSION}, for every company that was ever a "
        "member."
    )
    assert [line[3:] for line in out.splitlines() if line.startswith("## ")] == [
        "Gaps by company and year",
        "Prices",
        *METRICS,
    ]
    # Every company in the universe by then, Twitter included, though it left later.
    for row in (
        "| Apple Inc. (`apple`) |",
        "| Facebook, Inc. (`meta`) |",
        "| Tesla, Inc. (`tesla`) |",
        "| Twitter, Inc. (`twitter`) |",
    ):
        assert row in out


@pytest.mark.usefixtures("use_fixture_store")
def test_price_gaps_are_listed_by_company_and_year(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The fixture store has no bars for Tesla, which joined on December 21, 2020: its
    # sessions to May 28, 2021, the last to close before June 1's 09:30, are missing.
    # Consecutive ones are a range, across Christmas too.
    assert coverage.main(["--as-of", "2021-06-01", "--metric", "revenue"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert (
        "| Tesla, Inc. (`tesla`) | 2020 | 8 missing: 2020-12-21 to 2020-12-31 |  |"
        in lines
    )
    assert (
        "| Tesla, Inc. (`tesla`) | 2020-12-21 on | 110 | 110 | 0 | none |  |" in lines
    )
    # Apple's revenue gaps share a row with its price gaps.
    (apple,) = [
        line for line in lines if line.startswith("| Apple Inc. (`apple`) | 2021 |")
    ]
    assert apple.endswith("| revenue: 2021-03-27 |")


@pytest.mark.usefixtures("use_fixture_store")
def test_one_metric_at_a_time(capsys: pytest.CaptureFixture[str]) -> None:
    assert coverage.main(["--as-of", "2021-06-01", "--metric", "revenue"]) == 0

    out = capsys.readouterr().out
    assert "## revenue" in out
    assert "## net_income" not in out


@pytest.mark.usefixtures("use_fixture_store")
def test_an_unknown_universe_or_time_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert coverage.main(["--universe", "sp500"]) == 2
    assert "No such universe: sp500" in capsys.readouterr().err
    assert coverage.main(["--as-of", "yesterday"]) == 2
    assert "isn't a knowledge time" in capsys.readouterr().err
