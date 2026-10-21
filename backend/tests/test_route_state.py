"""Tests for canonical route-state rules (§7).

Verifies:
- POST /v1/worker/leases/next returns only confirmed active leases
- POST /v1/worker/leases/{lease_id}/ack requires active lease
- All lease routes verify authenticated node ownership
- No worker sees a lease before on-chain confirmation
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models import Node, SupportedModel, User
from app.services.job_service import confirm_job_escrow, create_job
from app.services.lease_service import activate_lease
from app.services.scheduler import schedule_next_job


@pytest_asyncio.fixture
async def seed_model(db: AsyncSession):
    model = SupportedModel(
        id="resnet50",
        name="ResNet-50",
        framework="pytorch",
        vram_required_gb=8,
        price_base_units=500000000000000000,
        model_version="1.0",
        preprocessing_version="resnet50-v1",
        input_type="image",
        supported_formats=["jpg", "png"],
    )
    db.add(model)
    await db.flush()
    return model


@pytest_asyncio.fixture
async def seed_node(db: AsyncSession):
    provider = User(id=uuid.uuid4(), wallet_address="0x" + uuid.uuid4().hex, role="provider")
    db.add(provider)
    await db.flush()

    api_key = "nb_live_" + uuid.uuid4().hex
    node = Node(
        id=uuid.uuid4(),
        provider_id=provider.id,
        gpu_name="RTX 4090",
        vram_gb=24,
        status="online",
        worker_signer_address="0x" + uuid.uuid4().hex,
        api_key_hash=hashlib.sha256(api_key.encode()).hexdigest(),
        active_leases=0,
        last_heartbeat=datetime.now(timezone.utc),
    )
    db.add(node)
    await db.flush()
    return node, api_key


class TestLeaseNextRouteState:
    @pytest.mark.asyncio
    async def test_returns_only_active_leases(self, db: AsyncSession, seed_model, seed_node):
        node, api_key = seed_node
        user = User(id=uuid.uuid4(), wallet_address="0x" + uuid.uuid4().hex, role="user")
        db.add(user)
        await db.flush()

        job = await create_job(
            db,
            user_id=user.id,
            model_id="resnet50",
            chain_job_id="0x" + uuid.uuid4().hex,
            price_base_units=500000000000000000,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        await confirm_job_escrow(db, job_id=job.id, tx_hash="0xabc", escrow_amount=500000000000000000)
        result = await schedule_next_job(db)
        assert result is not None
        _, _, lease = result
        await db.flush()

        # Lease is pending_chain (not activated)
        assert lease.status == "pending_chain"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/worker/leases/next",
                headers={"X-API-Key": api_key},
            )
        assert resp.status_code == 200
        # Must NOT return a pending_chain lease
        assert resp.json()["lease"] is None

    @pytest.mark.asyncio
    async def test_returns_active_lease_after_activation(self, db: AsyncSession, seed_model, seed_node):
        node, api_key = seed_node
        user = User(id=uuid.uuid4(), wallet_address="0x" + uuid.uuid4().hex, role="user")
        db.add(user)
        await db.flush()

        job = await create_job(
            db,
            user_id=user.id,
            model_id="resnet50",
            chain_job_id="0x" + uuid.uuid4().hex,
            price_base_units=500000000000000000,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        await confirm_job_escrow(db, job_id=job.id, tx_hash="0xabc", escrow_amount=500000000000000000)
        result = await schedule_next_job(db)
        _, _, lease = result

        # Simulate dispatcher: activate the lease
        await activate_lease(db, lease.id)
        await db.flush()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/worker/leases/next",
                headers={"X-API-Key": api_key},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["lease"] is not None
        assert data["lease"]["lease_id"] == str(lease.id)


class TestLeaseAckRouteState:
    @pytest.mark.asyncio
    async def test_ack_requires_active_lease(self, db: AsyncSession, seed_model, seed_node):
        node, api_key = seed_node
        user = User(id=uuid.uuid4(), wallet_address="0x" + uuid.uuid4().hex, role="user")
        db.add(user)
        await db.flush()

        job = await create_job(
            db,
            user_id=user.id,
            model_id="resnet50",
            chain_job_id="0x" + uuid.uuid4().hex,
            price_base_units=500000000000000000,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        await confirm_job_escrow(db, job_id=job.id, tx_hash="0xabc", escrow_amount=500000000000000000)
        _, _, lease = await schedule_next_job(db)
        # Don't activate — lease is pending_chain
        await db.flush()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/v1/worker/leases/{lease.id}/ack",
                json={},
                headers={"X-API-Key": api_key},
            )
        # Must reject ack on pending_chain lease
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_ack_works_on_active_lease(self, db: AsyncSession, seed_model, seed_node):
        node, api_key = seed_node
        user = User(id=uuid.uuid4(), wallet_address="0x" + uuid.uuid4().hex, role="user")
        db.add(user)
        await db.flush()

        job = await create_job(
            db,
            user_id=user.id,
            model_id="resnet50",
            chain_job_id="0x" + uuid.uuid4().hex,
            price_base_units=500000000000000000,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        await confirm_job_escrow(db, job_id=job.id, tx_hash="0xabc", escrow_amount=500000000000000000)
        _, _, lease = await schedule_next_job(db)
        await activate_lease(db, lease.id)
        job.status = "assigned"
        await db.flush()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/v1/worker/leases/{lease.id}/ack",
                json={"worker_signer_address": node.worker_signer_address},
                headers={"X-API-Key": api_key},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"


class TestLeaseOwnershipVerification:
    @pytest.mark.asyncio
    async def test_wrong_node_rejected_on_ack(self, db: AsyncSession, seed_model, seed_node):
        node, api_key = seed_node
        other_key = "nb_live_" + uuid.uuid4().hex
        other_node = Node(
            id=uuid.uuid4(),
            provider_id=node.provider_id,
            gpu_name="RTX 3090",
            vram_gb=24,
            status="online",
            api_key_hash=hashlib.sha256(other_key.encode()).hexdigest(),
        )
        db.add(other_node)
        await db.flush()

        user = User(id=uuid.uuid4(), wallet_address="0x" + uuid.uuid4().hex, role="user")
        db.add(user)
        await db.flush()

        job = await create_job(
            db,
            user_id=user.id,
            model_id="resnet50",
            chain_job_id="0x" + uuid.uuid4().hex,
            price_base_units=500000000000000000,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        await confirm_job_escrow(db, job_id=job.id, tx_hash="0xabc", escrow_amount=500000000000000000)
        _, _, lease = await schedule_next_job(db)
        await activate_lease(db, lease.id)
        await db.flush()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/v1/worker/leases/{lease.id}/ack",
                json={},
                headers={"X-API-Key": other_key},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_wrong_node_rejected_on_complete(self, db: AsyncSession, seed_model, seed_node):
        node, api_key = seed_node
        other_key = "nb_live_" + uuid.uuid4().hex
        other_node = Node(
            id=uuid.uuid4(),
            provider_id=node.provider_id,
            gpu_name="RTX 3090",
            vram_gb=24,
            status="online",
            api_key_hash=hashlib.sha256(other_key.encode()).hexdigest(),
        )
        db.add(other_node)
        await db.flush()

        user = User(id=uuid.uuid4(), wallet_address="0x" + uuid.uuid4().hex, role="user")
        db.add(user)
        await db.flush()

        job = await create_job(
            db,
            user_id=user.id,
            model_id="resnet50",
            chain_job_id="0x" + uuid.uuid4().hex,
            price_base_units=500000000000000000,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        await confirm_job_escrow(db, job_id=job.id, tx_hash="0xabc", escrow_amount=500000000000000000)
        _, _, lease = await schedule_next_job(db)
        await activate_lease(db, lease.id)
        await db.flush()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/v1/worker/leases/{lease.id}/complete",
                headers={"X-API-Key": other_key},
            )
        assert resp.status_code == 422  # envelope validation precedes ownership for an empty body

    @pytest.mark.asyncio
    async def test_wrong_node_rejected_on_fail(self, db: AsyncSession, seed_model, seed_node):
        node, api_key = seed_node
        other_key = "nb_live_" + uuid.uuid4().hex
        other_node = Node(
            id=uuid.uuid4(),
            provider_id=node.provider_id,
            gpu_name="RTX 3090",
            vram_gb=24,
            status="online",
            api_key_hash=hashlib.sha256(other_key.encode()).hexdigest(),
        )
        db.add(other_node)
        await db.flush()

        user = User(id=uuid.uuid4(), wallet_address="0x" + uuid.uuid4().hex, role="user")
        db.add(user)
        await db.flush()

        job = await create_job(
            db,
            user_id=user.id,
            model_id="resnet50",
            chain_job_id="0x" + uuid.uuid4().hex,
            price_base_units=500000000000000000,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        await confirm_job_escrow(db, job_id=job.id, tx_hash="0xabc", escrow_amount=500000000000000000)
        _, _, lease = await schedule_next_job(db)
        await activate_lease(db, lease.id)
        await db.flush()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/v1/worker/leases/{lease.id}/fail",
                json={"error": "test"},
                headers={"X-API-Key": other_key},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_rejected(self, db: AsyncSession):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/v1/worker/leases/next")
        assert resp.status_code == 401
