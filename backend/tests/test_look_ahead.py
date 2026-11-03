import ast
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.data.errors import NotFoundError
from app.data.look_ahead import LookAhead
from app.data.timeutil import parse_knowledge_time
from app.data.view import PointInTimeView
from tests.fixture_loader import FIXTURE_DATA_VERSION, FIXTURE_INGESTED_AT

BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND_DIR / "app"
LOOK_AHEAD = "app.data.look_ahead"
TICKERS = ("AAPL", "FB", "META", "MSFT", "JPM", "TSLA", "TWTR")


def look_ahead(store: Path, as_of: str) -> LookAhead:
    return LookAhead(
        parse_knowledge_time(as_of), data_version=FIXTURE_DATA_VERSION, store=store
    )


def test_the_horizon_is_the_data_versions_cut(fixture_store: Path) -> None:
    with look_ahead(fixture_store, "2020-06-05") as ahead:
        assert ahead.horizon == FIXTURE_INGESTED_AT


def test_without_a_data_version_the_horizon_is_now(fixture_store: Path) -> None:
    before = datetime.now(UTC)
    with LookAhead(parse_knowledge_time("2020-06-05"), store=fixture_store) as ahead:
        assert before <= ahead.horizon <= datetime.now(UTC)


@pytest.mark.parametrize(
    "as_of",
    ["2012-07-31", "2020-06-05", "2020-06-05T16:00", "2021-11-01", "2026-01-01"],
)
def test_every_read_comes_after_t_and_by_the_cut(
    fixture_store: Path, as_of: str
) -> None:
    knowledge_time = parse_knowledge_time(as_of)
    found = []
    with (
        PointInTimeView(
            knowledge_time, data_version=FIXTURE_DATA_VERSION, store=fixture_store
        ) as view,
        look_ahead(fixture_store, as_of) as ahead,
    ):
        for ticker in TICKERS:
            try:
                security = view.resolve_ticker(ticker)
            except NotFoundError:
                continue  # not in use then, such as META before June 2022
            found += [ahead.next_bar(security), *ahead.next_filings(security).values()]
            found += ahead.later_amendments(security)
            found += ahead.universe_changes(security)
            for quarter in view.get_fundamentals_as_of(ticker, "revenue", quarters=40):
                found += ahead.later_quarter_versions(security, quarter)
        for observation in view.get_macro_series_as_of("UNRATE"):
            found += ahead.later_versions(observation)

    moments = [record.available_at for record in found if record is not None]
    assert all(knowledge_time < moment <= FIXTURE_INGESTED_AT for moment in moments)


def test_reads_find_what_came_later(fixture_store: Path) -> None:
    # Without this, the test above would pass on reads that found nothing.
    with (
        PointInTimeView(
            parse_knowledge_time("2020-06-05"), store=fixture_store
        ) as view,
        look_ahead(fixture_store, "2020-06-05") as ahead,
    ):
        apple = view.resolve_ticker("AAPL")
        may = view.get_macro_as_of("UNRATE")
        assert may is not None

        assert ahead.next_bar(apple) is not None
        assert ahead.next_filings(apple)["10-Q"] is not None
        assert [f.accession_number for f in ahead.later_amendments(apple)] == [
            "0000320193-20-900001"
        ]
        assert [v.value for v in ahead.later_versions(may)] == [13.2]


def test_no_canary_row_is_ever_returned(fixture_store: Path) -> None:
    # Every fixture table has one for Apple or UNRATE, known only in 2099: after the
    # data version was cut.
    with (
        PointInTimeView(
            parse_knowledge_time("2020-06-05"), store=fixture_store
        ) as view,
        look_ahead(fixture_store, "2020-06-05") as ahead,
    ):
        apple = view.resolve_ticker("AAPL")
        january_1990 = view.get_macro_as_of("UNRATE", date(1990, 1, 1))
        assert january_1990 is not None

        assert ahead.universe_changes(apple) == []
        assert ahead.later_versions(january_1990) == []


def test_a_bad_limit_is_rejected(fixture_store: Path) -> None:
    with (
        PointInTimeView(
            parse_knowledge_time("2020-06-05"), store=fixture_store
        ) as view,
        look_ahead(fixture_store, "2020-06-05") as ahead,
        pytest.raises(ValueError, match="at least 1"),
    ):
        ahead.later_amendments(view.resolve_ticker("AAPL"), limit=0)


def module_name(path: Path, root: Path) -> str:
    """The dotted name of the module at `path`, under `root`: app.backtest.spec."""
    parts = path.relative_to(root).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def imports_of_look_ahead(folder: Path, root: Path = BACKEND_DIR) -> list[str]:
    """Every import of the look-ahead module in the Python files under `folder`, as
    "path:line" relative to it. Relative imports are resolved."""
    found = []
    for path in sorted(folder.rglob("*.py")):
        module = module_name(path, root)
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parent = package
                    for _ in range(node.level - 1):
                        parent = parent.rpartition(".")[0]
                    base = f"{parent}.{base}" if base else parent
                names = [base, *(f"{base}.{alias.name}" for alias in node.names)]
            else:
                continue
            if any(n == LOOK_AHEAD or n.startswith(f"{LOOK_AHEAD}.") for n in names):
                found.append(f"{path.relative_to(folder).as_posix()}:{node.lineno}")
    return found


def in_a_fresh_interpreter(code: str) -> str:
    """What `code` prints when run by a new Python process in backend/."""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return result.stdout.strip()


def test_the_backtest_engine_never_imports_the_look_ahead_module() -> None:
    engine = APP_DIR / "backtest"
    assert imports_of_look_ahead(engine) == []

    # Nor through another module: import the whole engine in a fresh interpreter.
    modules = [module_name(path, BACKEND_DIR) for path in sorted(engine.rglob("*.py"))]
    code = "\n".join(
        [
            "import importlib, sys",
            *(f"importlib.import_module({module!r})" for module in modules),
            f"print({LOOK_AHEAD!r} in sys.modules)",
        ]
    )
    assert in_a_fresh_interpreter(code) == "False"


@pytest.mark.parametrize(
    "line",
    [
        "import app.data.look_ahead",
        "from app.data import look_ahead",
        "from app.data.look_ahead import LookAhead",
        "from ..data import look_ahead",
    ],
)
def test_the_import_guard_catches_an_offender(tmp_path: Path, line: str) -> None:
    engine = tmp_path / "app" / "backtest"
    engine.mkdir(parents=True)
    (engine / "__init__.py").write_text("", encoding="utf-8")
    (engine / "signals.py").write_text(f'"""A signal."""\n{line}\n', encoding="utf-8")

    assert imports_of_look_ahead(engine, root=tmp_path) == ["signals.py:2"]


def test_only_the_snapshot_route_imports_it() -> None:
    # Keep it that way: the MCP tools (E10) mustn't either.
    assert [hit.split(":")[0] for hit in imports_of_look_ahead(APP_DIR)] == [
        "api/snapshot.py"
    ]


def test_the_fresh_interpreter_would_see_an_import() -> None:
    # Without this, the transitive check above could never fail.
    code = f"import sys, {LOOK_AHEAD}\nprint({LOOK_AHEAD!r} in sys.modules)"

    assert in_a_fresh_interpreter(code) == "True"
