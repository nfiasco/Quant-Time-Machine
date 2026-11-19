"""The API's OpenAPI schema, as the committed doc/reference/openapi.json holds it (S8.6).

The frontend generates its TypeScript types from that file (`npm run api:types` in
frontend/), so they follow the response models here without a server running.
tests/test_openapi.py fails when the file is out of date. From backend/, refresh it with

    uv run python -m app.api.openapi > ../doc/reference/openapi.json
"""

import json

from app.config import Settings
from app.main import create_app


def openapi_schema() -> str:
    """What `GET /openapi.json` serves, indented, with a final newline.

    The app is built from known settings, so a developer's backend/.env can't change it.
    """
    return json.dumps(create_app(Settings(_env_file=None)).openapi(), indent=2) + "\n"


if __name__ == "__main__":
    print(openapi_schema(), end="")
