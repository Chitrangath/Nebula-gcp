"""Health interface tests for hosted process supervision."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from app.database import get_db
from app.main import app


@pytest.mark.asyncio
async def test_liveness_does_not_require_database():
    async def unavailable_db():
        raise RuntimeError("database dependency must not be resolved for liveness")
        yield

    app.dependency_overrides[get_db] = unavailable_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await client.get("/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_checks_database(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        OperationalError("SELECT 1", {}, RuntimeError("database unavailable")),
        ConnectionRefusedError("database unavailable"),
    ],
)
async def test_readiness_returns_503_when_database_is_unavailable(failure: Exception):
    class UnavailableDatabase:
        async def execute(self, _statement):
            raise failure

    async def unavailable_db():
        yield UnavailableDatabase()

    app.dependency_overrides[get_db] = unavailable_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["detail"] == "Database is unavailable"
    assert body["status"] == 503
    assert body["instance"] == "/ready"
