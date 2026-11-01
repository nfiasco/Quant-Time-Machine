"""Shared test fixtures: temporary point-in-time stores, loaded from tests/fixtures/, and
API clients that read them."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.data.tables import TABLES
from app.data.versions import write_manifest
from app.main import create_app
from tests.fixture_loader import (
    FIXTURE_INGESTED_AT,
    FIXTURES,
    TEST_TABLES,
    load_fixture,
)


@pytest.fixture
def store_dir(tmp_path: Path) -> Path:
    """An empty point-in-time store in a temporary folder."""
    return tmp_path / "store"


@pytest.fixture
def fixture_store(store_dir: Path) -> Path:
    """A temporary store holding every table in tests/fixtures/, frozen as one data
    version, FIXTURE_DATA_VERSION, as an ingestion run would leave it."""
    known = TABLES | TEST_TABLES
    for path in sorted(FIXTURES.glob("*.csv")):
        spec = known.get(path.stem)
        if spec is None:
            pytest.fail(f"{path.name} matches no table in app/data/tables.py")
        load_fixture(store_dir, spec, path)
    write_manifest(store_dir, known.values(), now=FIXTURE_INGESTED_AT)
    return store_dir


def api_client(store: Path, *, serve_raw_prices: bool) -> TestClient:
    """The API reading `store`, built from known settings, so a developer's
    backend/.env can't change the results."""
    settings = Settings(
        _env_file=None, data_dir=store.parent, serve_raw_prices=serve_raw_prices
    )
    return TestClient(create_app(settings))


@pytest.fixture
def client(fixture_store: Path) -> TestClient:
    """The API reading the fixture store, with raw prices on, as on your own machine."""
    return api_client(fixture_store, serve_raw_prices=True)


@pytest.fixture
def restricted_client(fixture_store: Path) -> TestClient:
    """The API as a public deployment runs it: raw prices off (D2)."""
    return api_client(fixture_store, serve_raw_prices=False)
