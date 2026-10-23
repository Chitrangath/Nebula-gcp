"""BE-003 provider node ownership and credential lifecycle tests."""

import hashlib

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models import User
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
