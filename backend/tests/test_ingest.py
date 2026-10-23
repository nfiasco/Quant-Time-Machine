import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest

from app.config import BACKEND_DIR, Settings
from app.data import ingest
from app.data.http import FetchError, RateLimitExceeded
from app.data.ingest import INGESTERS, IngestContext, main
from app.data.sources import IngestError, alfred, edgar


@pytest.fixture
def use_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Make the CLI use these settings instead of reading backend/.env."""

    def use(**values: object) -> None:
        settings = Settings(_env_file=None, data_dir=tmp_path, **values)
        monkeypatch.setattr(ingest, "get_settings", lambda: settings)

    return use


def test_runs_the_sources_ingester(
    monkeypatch: pytest.MonkeyPatch, use_settings, tmp_path: Path
) -> None:
    calls: list[IngestContext] = []
    monkeypatch.setitem(INGESTERS, "fred", calls.append)
    use_settings(fred_api_key="test-key")

    assert main(["fred", "--refresh"]) == 0

    [context] = calls
    assert context.client.config.name == "fred"
    assert context.client.refresh is True
    assert context.store == tmp_path / "store"


def test_a_source_without_an_ingester_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delitem(INGESTERS, "sec")

    assert main(["sec"]) == 2
    assert "No ingester for sec yet" in capsys.readouterr().err


def test_a_missing_key_exits_2(
    monkeypatch: pytest.MonkeyPatch, use_settings, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(INGESTERS, "tiingo", lambda context: None)
    use_settings()

    assert main(["tiingo"]) == 2
    assert "TIINGO_API_KEY isn't set" in capsys.readouterr().err


def test_a_rate_limit_stops_the_run_with_exit_1(
    monkeypatch: pytest.MonkeyPatch, use_settings, capsys: pytest.CaptureFixture[str]
) -> None:
    def ingester(context: IngestContext) -> None:
        raise RateLimitExceeded("tiingo", datetime(2026, 10, 19, 13, tzinfo=UTC))

    monkeypatch.setitem(INGESTERS, "tiingo", ingester)
    use_settings(tiingo_api_key="test-token")

    assert main(["tiingo"]) == 1
    assert "picks up where it stopped" in capsys.readouterr().err


@pytest.mark.parametrize(
    "error",
    [
        FetchError("fred: GET series failed after 4 attempts: HTTP 500"),
        IngestError("UNRATE: FRED says it comes from release 99"),
    ],
)
def test_a_failed_ingest_exits_1_with_its_message(
    monkeypatch: pytest.MonkeyPatch,
    use_settings,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    def ingester(context: IngestContext) -> None:
        raise error

    monkeypatch.setitem(INGESTERS, "fred", ingester)
    use_settings(fred_api_key="test-key")

    assert main(["fred"]) == 1
    assert str(error) in capsys.readouterr().err


def test_request_urls_with_keys_are_never_logged(
    monkeypatch: pytest.MonkeyPatch, use_settings, caplog: pytest.LogCaptureFixture
) -> None:
    # httpx2 logs every request URL at INFO, and FRED's URLs carry the API key.
    caplog.set_level(logging.INFO)
    answer = httpx2.MockTransport(lambda request: httpx2.Response(200, json={}))
    real_client_for = ingest.client_for
    monkeypatch.setattr(
        ingest,
        "client_for",
        lambda *args, **options: real_client_for(*args, transport=answer, **options),
    )
    monkeypatch.setitem(
        INGESTERS, "fred", lambda context: context.client.get("series", {"x": "1"})
    )
    use_settings(fred_api_key="fredsecret0123456789")

    assert main(["fred"]) == 0
    assert "fredsecret0123456789" not in caplog.text


def test_fred_runs_the_alfred_ingester() -> None:
    assert INGESTERS["fred"] is alfred.ingest


def test_sec_runs_the_edgar_ingester() -> None:
    assert INGESTERS["sec"] is edgar.ingest


def test_unknown_sources_are_usage_errors() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["wrds"])

    assert caught.value.code == 2


def test_runs_as_a_module() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.data.ingest", "--help"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "{fred,sec,tiingo}" in result.stdout
    assert "--refresh" in result.stdout
