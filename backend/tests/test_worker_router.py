"""Tests for the canonical worker API router (lease-scoped)."""

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
async def seed_provider(db: AsyncSession):
    provider = User(
        id=uuid.uuid4(),
        wallet_address="0x" + uuid.uuid4().hex,
        role="provider",
    )
    db.add(provider)
    await db.flush()
    return provider


@pytest_asyncio.fixture
async def seed_node(db: AsyncSession, seed_provider):
    api_key = "nb_live_" + uuid.uuid4().hex
    node = Node(
        id=uuid.uuid4(),
        provider_id=seed_provider.id,
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


class TestLeaseNext:
    @pytest.mark.asyncio
    async def test_lease_next_no_jobs(self, db: AsyncSession, seed_node):
        node, api_key = seed_node
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/worker/leases/next",
                headers={"X-API-Key": api_key},
            )
        assert resp.status_code == 200
        assert resp.json()["lease"] is None

    @pytest.mark.asyncio
    async def test_lease_next_with_job(self, db: AsyncSession, seed_model, seed_node):
        """Scheduler creates pending_chain lease; /leases/next returns None until activated."""
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
        await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/worker/leases/next",
                headers={"X-API-Key": api_key},
            )
        assert resp.status_code == 200
        # Lease is pending_chain (not activated by dispatcher), so None is returned
        data = resp.json()
        assert data["lease"] is None

    @pytest.mark.asyncio
    async def test_lease_next_unauthenticated(self, db: AsyncSession):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/v1/worker/leases/next")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_lease_next_does_not_redeliver_after_proof_is_queued(
        self, db: AsyncSession, seed_model, seed_node
    ):
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
        from app.services.lease_service import activate_lease

        await activate_lease(db, lease.id)
        job.status = "verifying"
        await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/v1/worker/leases/next", headers={"X-API-Key": api_key})

        assert resp.status_code == 200
        assert resp.json()["lease"] is None


class TestLeaseAck:
    @pytest.mark.asyncio
    async def test_ack_activates_lease(self, db: AsyncSession, seed_model, seed_node):
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

        # Simulate backend dispatcher: activate the pending_chain lease
        from app.services.lease_service import activate_lease

        await activate_lease(db, lease.id)
        job.status = "assigned"
        await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/v1/worker/leases/{lease.id}/ack",
                json={"worker_signer_address": node.worker_signer_address},
                headers={"X-API-Key": api_key},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_ack_wrong_node(self, db: AsyncSession, seed_model, seed_node):
        node, api_key = seed_node
        other_api_key = "nb_live_" + uuid.uuid4().hex
        other_node = Node(
            id=uuid.uuid4(),
            provider_id=node.provider_id,
            gpu_name="RTX 3090",
            vram_gb=24,
            status="online",
            api_key_hash=hashlib.sha256(other_api_key.encode()).hexdigest(),
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
        result = await schedule_next_job(db)
        assert result is not None
        _, _, lease = result

        # Activate the lease (simulating backend dispatcher)
        from app.services.lease_service import activate_lease

        await activate_lease(db, lease.id)
        await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/v1/worker/leases/{lease.id}/ack",
                json={},
                headers={"X-API-Key": other_api_key},
            )
        assert resp.status_code == 403


class TestLeaseComplete:
    @pytest.mark.asyncio
    async def test_complete_lease(self, db: AsyncSession, seed_model, seed_node):
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

        # Activate the lease first
        from app.services.lease_service import activate_lease

        await activate_lease(db, lease.id)
        await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/v1/worker/leases/{lease.id}/complete",
                headers={"X-API-Key": api_key},
            )
        assert resp.status_code == 422  # canonical proof envelope is mandatory


class TestLeaseFail:
    @pytest.mark.asyncio
    async def test_fail_lease(self, db: AsyncSession, seed_model, seed_node):
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
        await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/v1/worker/leases/{lease.id}/fail",
                json={"error": "GPU OOM"},
                headers={"X-API-Key": api_key},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"


class TestNodeHeartbeat:
    @pytest.mark.asyncio
    async def test_authenticated_heartbeat_activates_pending_node(self, db: AsyncSession, seed_node):
        node, api_key = seed_node
        node.status = "pending"
        await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/v1/worker/nodes/{node.id}/heartbeat",
                headers={"X-API-Key": api_key},
            )

        await db.refresh(node)
        assert resp.status_code == 200
        assert node.status == "online"

    @pytest.mark.asyncio
    async def test_heartbeat(self, db: AsyncSession, seed_node):
        node, api_key = seed_node
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/v1/worker/nodes/{node.id}/heartbeat",
                headers={"X-API-Key": api_key},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_heartbeat_wrong_node_id(self, db: AsyncSession, seed_node):
        node, api_key = seed_node
        fake_id = str(uuid.uuid4())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/v1/worker/nodes/{fake_id}/heartbeat",
                headers={"X-API-Key": api_key},
            )
        assert resp.status_code == 403
