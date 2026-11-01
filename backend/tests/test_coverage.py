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
        "# Fundamentals coverage\n\n`starter_large_caps` as known at June 1, 2021, "
        f"9:30 AM ET, data version {FIXTURE_DATA_VERSION}:"
    )
    assert [line[3:] for line in out.splitlines() if line.startswith("## ")] == list(
        METRICS
    )
    # Every company in the universe by then, Twitter included, though it left later.
    for row in (
        "| Apple Inc. (`apple`) |",
        "| Facebook, Inc. (`meta`) |",
        "| Tesla, Inc. (`tesla`) |",
        "| Twitter, Inc. (`twitter`) |",
    ):
        assert row in out


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
