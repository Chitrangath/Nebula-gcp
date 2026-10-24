"""DEMO-007 authenticated network projection tests."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.models import Job, Lease, SupportedModel, User
from app.routers import network as network_router
from app.services.node_service import register_node
from tests.conftest import seed_authed_user


@pytest.mark.asyncio
async def test_network_snapshot_exposes_public_device_state_without_credentials(db, monkeypatch):
    viewer_id, token = await seed_authed_user(db)
    verifier_address = "0x" + "38" * 20
    monkeypatch.setattr(settings, "CONTRACT_VERIFIER_ADDRESS", verifier_address)
    provider_one = User(wallet_address="0x" + "40" * 20, role="provider")
    provider_two = User(wallet_address="0x" + "50" * 20, role="provider")
    db.add_all(
        [
            provider_one,
            provider_two,
            SupportedModel(id="resnet50", name="ResNet-50", price_base_units=50_000),
            SupportedModel(id="bert-base", name="BERT sentiment", price_base_units=50_000),
        ]
    )
    await db.flush()
    first, _ = await register_node(db, provider_one.id, "RTX 3050", 4, "IN", "0x" + "11" * 20)
    second, _ = await register_node(db, provider_two.id, "RTX 5050", 8, "IN", "0x" + "22" * 20)
    monkeypatch.setattr(settings, "DEMO_VERIFIER_NODE_ID", str(first.id))
    now = datetime.now(timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz is not None else now.replace(tzinfo=None)

    monkeypatch.setattr(network_router, "datetime", FrozenDateTime)
    first.status = "online"
    first.supports_bert = True
    first.last_heartbeat = now - timedelta(seconds=15)
    second.status = "online"
    second.last_heartbeat = now - timedelta(
        seconds=settings.NODE_HEARTBEAT_TTL_SECONDS, milliseconds=1
    )
    active_job = Job(
        user_id=viewer_id,
        model_id="bert-base",
        chain_job_id="0x" + "aa" * 32,
        assigned_node_id=first.id,
        status="assigned",
        price_base_units=50_000,
        deadline=now + timedelta(hours=1),
    )
    completed_job = Job(
        user_id=viewer_id,
        model_id="resnet50",
        chain_job_id="0x" + "bb" * 32,
        assigned_node_id=first.id,
        status="completed",
        price_base_units=50_000,
        deadline=now + timedelta(hours=1),
        completed_at=now - timedelta(minutes=2),
    )
    older_completed_job = Job(
        user_id=viewer_id,
        model_id="bert-base",
        chain_job_id="0x" + "dd" * 32,
        assigned_node_id=first.id,
        status="completed",
        price_base_units=50_000,
        deadline=now + timedelta(hours=1),
        completed_at=now - timedelta(minutes=5),
    )
    db.add_all([active_job, completed_job, older_completed_job])
    await db.flush()
    lease = Lease(
        job_id=active_job.id,
        node_id=first.id,
        lease_id="0x" + "cc" * 32,
        status="active",
        expires_at=now + timedelta(minutes=5),
    )
    db.add(lease)
    await db.flush()
    active_job.current_lease_id = lease.id
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/network", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["chain_id"] == settings.CHAIN_ID
    assert body["viewer"]["user_id"] == str(viewer_id)
    assert body["viewer"]["role"] == "ai_user"
    assert body["verifier_address"].lower() == verifier_address.lower()
    assert {node["gpu_name"] for node in body["nodes"]} == {"RTX 3050", "RTX 5050"}
    nodes_by_name = {node["gpu_name"]: node for node in body["nodes"]}
    online = nodes_by_name["RTX 3050"]
    stale = nodes_by_name["RTX 5050"]
    assert online["provider_wallet_address"].lower() == provider_one.wallet_address.lower()
    assert online["roles"] == ["gpu_provider", "verifier"]
    assert online["status"] == "online"
    assert 0 <= online["heartbeat_age_seconds"] < settings.NODE_HEARTBEAT_TTL_SECONDS
    assert online["supported_models"] == ["resnet50", "bert-base"]
    assert online["active_lease"]["chain_job_id"] == active_job.chain_job_id
    assert online["last_completed_job"]["chain_job_id"] == completed_job.chain_job_id
    assert stale["roles"] == ["gpu_provider"]
    assert stale["status"] == "offline"
    assert stale["heartbeat_age_seconds"] >= settings.NODE_HEARTBEAT_TTL_SECONDS
    assert "api_key" not in response.text
    assert "api_key_hash" not in response.text
    assert "worker_signer" not in response.text


@pytest.mark.asyncio
async def test_network_snapshot_requires_wallet_authentication(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/network")

    assert response.status_code == 401
