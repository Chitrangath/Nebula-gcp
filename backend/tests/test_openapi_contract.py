"""BE-003 checked OpenAPI contract drift gate."""

import json
from pathlib import Path

import pytest

from app.main import app


@pytest.mark.asyncio
async def test_checked_openapi_document_matches_fastapi() -> None:
    checked = Path(__file__).resolve().parents[1] / "openapi.json"
    rendered = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if checked.read_text() != rendered:
        raise AssertionError("backend/openapi.json is stale; run scripts/generate_openapi_contract.py")
