"""BE-003 provider node ownership and credential lifecycle tests."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models import Job, Lease, SupportedModel, User
from app.services.node_service import register_node
from tests.conftest import seed_authed_user


@pytest.mark.asyncio
async def test_node_registration_rejects_non_provider(db):
    _, token = await seed_authed_user(db)
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/nodes",
            json={"gpu_name": "Unauthorized GPU", "vram_gb": 24},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Provider role required"


@pytest.mark.asyncio
async def test_node_listing_is_authenticated_and_provider_scoped(db):
    provider_id, token = await seed_authed_user(db)
    provider = (await db.execute(select(User).where(User.id == provider_id))).scalar_one()
    provider.role = "provider"
    other = User(wallet_address="0x" + "44" * 20, role="provider")
    db.add(other)
    await db.flush()
    owned, _ = await register_node(db, provider.id, "Owned GPU", 24, "IN", None)
    await register_node(db, other.id, "Other GPU", 48, "US", None)
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/nodes", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert [node["id"] for node in response.json()] == [str(owned.id)]
    assert "api_key" not in response.text
    assert "api_key_hash" not in response.text


@pytest.mark.asyncio
async def test_node_listing_includes_capabilities_active_lease_and_recent_completed_work(db):
    provider_id, token = await seed_authed_user(db)
    provider = (await db.execute(select(User).where(User.id == provider_id))).scalar_one()
    provider.role = "provider"
    customer = User(wallet_address="0x" + "98" * 20, role="user")
    model = SupportedModel(id="bert-base", name="BERT sentiment", price_base_units=50_000)
    db.add_all([customer, model])
    await db.flush()
    node, _ = await register_node(db, provider.id, "RTX 3050", 4, "IN", None)
    node.status = "online"
    node.supports_bert = True
    active_job = Job(
        user_id=customer.id,
        model_id=model.id,
        chain_job_id="0x" + "11" * 32,
        assigned_node_id=node.id,
        status="assigned",
        price_base_units=50_000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    completed_job = Job(
        user_id=customer.id,
        model_id=model.id,
        chain_job_id="0x" + "22" * 32,
        assigned_node_id=node.id,
        status="completed",
        price_base_units=50_000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        completed_at=datetime.now(timezone.utc),
    )
    db.add_all([active_job, completed_job])
    await db.flush()
    lease = Lease(
        job_id=active_job.id,
        node_id=node.id,
        lease_id="0x" + "33" * 32,
        status="active",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db.add(lease)
    await db.flush()
    active_job.current_lease_id = lease.id
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/nodes", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    item = response.json()[0]
    assert item["supported_models"] == ["resnet50", "bert-base"]
    assert item["active_lease"]["job_id"] == str(active_job.id)
    assert item["active_lease"]["model_id"] == "bert-base"
    assert item["recent_jobs"][0]["job_id"] == str(completed_job.id)
    assert item["recent_jobs"][0]["model_id"] == "bert-base"
    assert item["recent_jobs"][0]["status"] == "completed"
    completed_at = datetime.fromisoformat(item["recent_jobs"][0]["completed_at"].replace("Z", "+00:00"))
    assert completed_at == completed_job.completed_at


@pytest.mark.asyncio
async def test_node_credentials_rotate_once_and_reject_cross_provider(db):
    provider_id, token = await seed_authed_user(db)
    provider = (await db.execute(select(User).where(User.id == provider_id))).scalar_one()
    provider.role = "provider"
    other = User(wallet_address="0x" + "55" * 20, role="provider")
    db.add(other)
    await db.flush()
    owned, old_key = await register_node(db, provider.id, "Owned GPU", 24, "IN", None)
    foreign, _ = await register_node(db, other.id, "Other GPU", 48, "US", None)
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            f"/v1/nodes/{foreign.id}/credentials/rotate",
            headers={"Authorization": f"Bearer {token}"},
        )
        response = await client.post(
            f"/v1/nodes/{owned.id}/credentials/rotate",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert denied.status_code == 404
    assert response.status_code == 200
    payload = response.json()
    assert payload["node_id"] == str(owned.id)
    assert payload["api_key"].startswith("nb_live_")
    assert payload["api_key"] != old_key
    await db.refresh(owned)
    assert owned.api_key_hash == hashlib.sha256(payload["api_key"].encode()).hexdigest()


@pytest.mark.asyncio
async def test_node_signer_rotation_replaces_stale_signer(db):
    provider_id, token = await seed_authed_user(db)
    provider = (await db.execute(select(User).where(User.id == provider_id))).scalar_one()
    provider.role = "provider"
    old_signer = "0x" + "66" * 20
    new_signer = "0x" + "77" * 20
    node, _ = await register_node(db, provider.id, "Owned GPU", 24, "IN", old_signer)
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/v1/nodes/{node.id}/worker-signer/rotate",
            json={"worker_signer_address": new_signer},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == {"node_id": str(node.id), "worker_signer_address": new_signer}
    await db.refresh(node)
    assert node.worker_signer_address == new_signer


@pytest.mark.asyncio
async def test_node_credential_revocation_disables_key(db):
    provider_id, token = await seed_authed_user(db)
    provider = (await db.execute(select(User).where(User.id == provider_id))).scalar_one()
    provider.role = "provider"
    node, old_key = await register_node(db, provider.id, "Owned GPU", 24, "IN", None)
    old_hash = node.api_key_hash
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/v1/nodes/{node.id}/credentials/revoke",
            headers={"Authorization": f"Bearer {token}"},
        )
        heartbeat = await client.post(
            f"/v1/worker/nodes/{node.id}/heartbeat",
            headers={"X-API-Key": old_key},
        )

    assert response.status_code == 204
    assert heartbeat.status_code == 401
    await db.refresh(node)
    assert node.status == "disabled"
    assert node.api_key_hash != old_hash
