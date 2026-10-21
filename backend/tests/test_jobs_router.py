"""Tests for the jobs API router (PRD v3.1 §16)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models import SupportedModel
from tests.conftest import seed_authed_user
from tests.vectors import PNG_1X1


async def create_job_request(client: AsyncClient, token: str) -> Response:
    return await client.post(
        "/v1/jobs",
        data={
            "model_id": "resnet50",
            "deadline": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
        files={"input_file": ("input.png", PNG_1X1, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest_asyncio.fixture
async def seed_model(db: AsyncSession) -> SupportedModel:
    model = SupportedModel(
        id="resnet50",
        name="ResNet-50",
        framework="pytorch",
        vram_required_gb=8,
        price_base_units=500000000000000000,
        model_version="1.0",
        preprocessing_version="resnet50-v1",
        model_hash_sha256="ab" * 32,
        max_input_size_mb=1,
        input_type="image",
        supported_formats=["jpg", "png"],
    )
    db.add(model)
    await db.flush()
    return model


@pytest.mark.asyncio
async def test_create_job_endpoint(db: AsyncSession, seed_model):
    user_id, token = await seed_authed_user(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await create_job_request(client, token)
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_id"] == "resnet50"
    assert data["status"] == "pending_blockchain"
    assert data["chain_job_id"] is not None


@pytest.mark.asyncio
async def test_list_jobs_empty(db: AsyncSession):
    user_id, token = await seed_authed_user(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/v1/jobs",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["jobs"] == []


@pytest.mark.asyncio
async def test_get_job_not_found(db: AsyncSession):
    user_id, token = await seed_authed_user(db)
    fake_id = str(uuid.uuid4())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/v1/jobs/{fake_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_job_unauthorized(db: AsyncClient):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/jobs",
            json={
                "model_id": "resnet50",
                "price_base_units": "500000000000000000",
                "deadline": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            },
        )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_confirm_escrow(db: AsyncSession, seed_model):
    """Client-supplied escrow authority is rejected by the strict schema."""
    from app.services.blockchain_service import FakeBlockchainBackend

    app.state.blockchain = FakeBlockchainBackend()
    user_id, token = await seed_authed_user(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a job first
        create_resp = await create_job_request(client, token)
        job_id = create_resp.json()["id"]

        # Confirm escrow
        resp = await client.post(
            f"/v1/jobs/{job_id}/confirm-escrow",
            json={
                "tx_hash": "0xabcdef1234567890",
                "escrow_amount": "500000000000000000",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_confirm_escrow_not_your_job(db: AsyncSession, seed_model):
    from app.services.blockchain_service import FakeBlockchainBackend

    app.state.blockchain = FakeBlockchainBackend()
    user_id, token = await seed_authed_user(db)
    other_id, other_token = await seed_authed_user(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await create_job_request(client, token)
        job_id = create_resp.json()["id"]

        resp = await client.post(
            f"/v1/jobs/{job_id}/confirm-escrow",
            json={
                "tx_hash": "0xabcdef1234567890",
            },
            headers={"Authorization": f"Bearer {other_token}"},
        )
    assert resp.status_code == 403
