import dataclasses
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.filings import Filing
from app.api.macro import MacroObservation
from app.api.prices import PriceBar
from app.config import Settings
from app.data import records
from app.main import create_app

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
        "ErrorResponse",
    } <= set(SPEC["components"]["schemas"])


@pytest.mark.parametrize(
    ("model", "record"),
    [
        (MacroObservation, records.MacroObservation),
        (PriceBar, records.PriceBar),
        (Filing, records.Filing),
    ],
)
def test_response_models_carry_every_record_field_but_internal_ids(
    model: type[BaseModel], record: type
) -> None:
    fields = {field.name for field in dataclasses.fields(record)}

    assert set(model.model_fields) == fields - {"security_id"}
