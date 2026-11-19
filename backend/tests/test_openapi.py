from pathlib import Path

from app.api.openapi import openapi_schema

REPOSITORY = Path(__file__).resolve().parents[2]
SCHEMA_FILE = REPOSITORY / "doc" / "reference" / "openapi.json"


def test_the_committed_openapi_schema_is_current() -> None:
    # The frontend's TypeScript types are generated from this file (S8.6).
    assert SCHEMA_FILE.read_text(encoding="utf-8") == openapi_schema(), (
        "doc/reference/openapi.json is out of date. From backend/, run "
        "uv run python -m app.api.openapi > ../doc/reference/openapi.json, "
        "then npm run api:types from frontend/"
    )
