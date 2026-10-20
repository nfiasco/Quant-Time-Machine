"""Shared test fixtures: temporary point-in-time stores, loaded from tests/fixtures/."""

from pathlib import Path

import pytest

from app.data.tables import TABLES
from tests.fixture_loader import FIXTURES, TEST_TABLES, load_fixture


@pytest.fixture
def store_dir(tmp_path: Path) -> Path:
    """An empty point-in-time store in a temporary folder."""
    return tmp_path / "store"


@pytest.fixture
def fixture_store(store_dir: Path) -> Path:
    """A temporary store holding every table in tests/fixtures/."""
    known = TABLES | TEST_TABLES
    for path in sorted(FIXTURES.glob("*.csv")):
        spec = known.get(path.stem)
        if spec is None:
            pytest.fail(f"{path.name} matches no table in app/data/tables.py")
        load_fixture(store_dir, spec, path)
    return store_dir
