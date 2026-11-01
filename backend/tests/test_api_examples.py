import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.examples import EXAMPLE_DATA_VERSION
from app.api.filings import Filing
from app.api.fundamentals import Fundamental
from app.api.macro import MacroObservation
from app.api.prices import PriceBar
from app.config import Settings
from app.data import records
from app.data.versions import latest_data_version
from app.main import create_app
from tests.fixture_loader import FIXTURE_DATA_VERSION

SPEC = create_app(Settings(_env_file=None)).openapi()


def documented_examples() -> list[Any]:
    """Every response example in the OpenAPI spec, with the status it documents."""
    found = []
    for path, operations in SPEC["paths"].items():
        for method, operation in operations.items():
            for status, response in operation["responses"].items():
                content = response.get("content", {}).get("application/json", {})
                for name, example in content.get("examples", {}).items():
                    label = f"{method.upper()} {path} {status} {name}"
                    found.append(pytest.param(int(status), example, id=label))
    return found


@pytest.mark.parametrize(("status", "example"), documented_examples())
def test_every_example_is_what_the_api_answers(
    client: TestClient,
    restricted_client: TestClient,
    status: int,
    example: dict[str, Any],
) -> None:
    # Each example's description is the request that produces it.
    method, url = example["description"].split(" ", 1)
    replay = restricted_client if status == 403 else client

    response = replay.request(method, url)

    assert (response.status_code, response.json()) == (status, example["value"])


def test_examples_show_the_fixture_stores_data_version(fixture_store: Path) -> None:
    assert EXAMPLE_DATA_VERSION == FIXTURE_DATA_VERSION
    assert latest_data_version(fixture_store) == FIXTURE_DATA_VERSION


def test_every_v1_operation_documents_its_errors() -> None:
    error = {"$ref": "#/components/schemas/ErrorResponse"}

    assert "HTTPValidationError" not in json.dumps(SPEC)
    for path, operations in SPEC["paths"].items():
        if not path.startswith("/v1/"):
            continue
        for operation in operations.values():
            for status in ("422", "500"):
                content = operation["responses"][status]["content"]
                assert content["application/json"]["schema"] == error, (path, status)


def test_response_models_have_readable_names() -> None:
    assert {
        "MacroResponse",
        "MacroObservation",
        "PriceResponse",
        "PriceBar",
        "FilingResponse",
        "FilingListResponse",
        "Filing",
        "FundamentalListResponse",
        "Fundamental",
        "ErrorResponse",
    } <= set(SPEC["components"]["schemas"])


@pytest.mark.parametrize(
    ("model", "record"),
    [
        (MacroObservation, records.MacroObservation),
        (PriceBar, records.PriceBar),
        (Filing, records.Filing),
        (Fundamental, records.Fundamental),
    ],
)
def test_response_models_carry_every_record_field_but_internal_ids(
    model: type[BaseModel], record: type
) -> None:
    fields = {field.name for field in dataclasses.fields(record)}

    assert set(model.model_fields) == fields - {"security_id"}
