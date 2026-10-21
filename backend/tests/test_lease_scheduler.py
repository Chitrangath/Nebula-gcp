"""Tests for the lease and scheduler services (PRD v3.1 §10, §13)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lease, Node, SupportedModel, User
from app.services.job_service import confirm_job_escrow, create_job
from app.services.lease_service import (
    complete_lease,
    create_lease,
    expire_overdue_leases,
    fail_lease,
    get_active_lease_for_job,
    heartbeat_lease,
)
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
async def seed_user(db: AsyncSession):
    user = User(
        id=uuid.uuid4(),
        wallet_address="0x" + uuid.uuid4().hex,
        role="user",
    )
    db.add(user)
    await db.flush()
    return user


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
    import hashlib

    node = Node(
        id=uuid.uuid4(),
        provider_id=seed_provider.id,
        gpu_name="RTX 4090",
        vram_gb=24,
        status="online",
        worker_signer_address="0x" + uuid.uuid4().hex,
        api_key_hash=hashlib.sha256(b"test-key").hexdigest(),
        active_leases=0,
        last_heartbeat=datetime.now(timezone.utc),
    )
    db.add(node)
    await db.flush()
    return node


@pytest_asyncio.fixture
async def seed_queued_job(db: AsyncSession, seed_model, seed_user):
    job = await create_job(
        db,
        user_id=seed_user.id,
        model_id="resnet50",
        chain_job_id="0x" + uuid.uuid4().hex,
        price_base_units=500000000000000000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    await confirm_job_escrow(
        db,
        job_id=job.id,
        tx_hash="0x" + uuid.uuid4().hex,
        escrow_amount=500000000000000000,
    )
    await db.commit()
    return job


class TestLeaseService:
    @pytest.mark.asyncio
    async def test_create_lease(self, db: AsyncSession, seed_queued_job, seed_node):
        lease = await create_lease(
            db,
            job_id=seed_queued_job.id,
            node_id=seed_node.id,
            lease_duration_minutes=30,
        )
        assert lease is not None
        assert lease.status == "pending_chain"
        assert lease.job_id == seed_queued_job.id
        assert lease.node_id == seed_node.id
        assert lease.lease_id is not None
        assert len(lease.lease_id) == 66  # 0x + 64 hex

    @pytest.mark.asyncio
    async def test_get_active_lease(self, db: AsyncSession, seed_queued_job, seed_node):
        from app.services.lease_service import activate_lease

        lease = await create_lease(
            db,
            job_id=seed_queued_job.id,
            node_id=seed_node.id,
            lease_duration_minutes=30,
        )
        await db.flush()

        # get_active_lease_for_job only returns active leases (not pending_chain)
        active = await get_active_lease_for_job(db, seed_queued_job.id)
        assert active is None  # Not active yet

        # Activate the lease
        await activate_lease(db, lease.id)

        active = await get_active_lease_for_job(db, seed_queued_job.id)
        assert active is not None
        assert active.id == lease.id

    @pytest.mark.asyncio
    async def test_get_active_lease_none(self, db: AsyncSession, seed_queued_job):
        active = await get_active_lease_for_job(db, seed_queued_job.id)
        assert active is None

    @pytest.mark.asyncio
    async def test_heartbeat_lease(self, db: AsyncSession, seed_queued_job, seed_node):
        lease = await create_lease(
            db,
            job_id=seed_queued_job.id,
            node_id=seed_node.id,
            lease_duration_minutes=30,
        )
        await db.flush()

        updated = await heartbeat_lease(db, lease.id)
        assert updated.heartbeat_at is not None

    @pytest.mark.asyncio
    async def test_complete_lease(self, db: AsyncSession, seed_queued_job, seed_node):
        lease = await create_lease(
            db,
            job_id=seed_queued_job.id,
            node_id=seed_node.id,
            lease_duration_minutes=30,
        )
        await db.flush()

        completed = await complete_lease(db, lease.id)
        assert completed.status == "completed"

    @pytest.mark.asyncio
    async def test_fail_lease(self, db: AsyncSession, seed_queued_job, seed_node):
        lease = await create_lease(
            db,
            job_id=seed_queued_job.id,
            node_id=seed_node.id,
            lease_duration_minutes=30,
        )
        await db.flush()

        failed = await fail_lease(db, lease.id)
        assert failed.status == "failed"

    @pytest.mark.asyncio
    async def test_expire_overdue_leases(self, db: AsyncSession, seed_queued_job, seed_node):
        lease = await create_lease(
            db,
            job_id=seed_queued_job.id,
            node_id=seed_node.id,
            lease_duration_minutes=0,  # expires immediately
        )
        await db.flush()

        expired_count = await expire_overdue_leases(db)
        assert expired_count >= 1

        # Verify lease is expired
        from sqlalchemy import select

        result = await db.execute(select(Lease).where(Lease.id == lease.id))
        updated_lease = result.scalar_one()
        assert updated_lease.status == "expired"


class TestScheduler:
    @pytest.mark.asyncio
    async def test_schedule_next_job(self, db: AsyncSession, seed_queued_job, seed_node):
        result = await schedule_next_job(db)
        assert result is not None
        job, node, lease = result
        assert job.id == seed_queued_job.id
        assert node.id == seed_node.id
        assert lease is not None

    @pytest.mark.asyncio
    async def test_schedule_no_queued_jobs(self, db: AsyncSession, seed_node):
        result = await schedule_next_job(db)
        assert result is None

    @pytest.mark.asyncio
    async def test_schedule_no_online_nodes(self, db: AsyncSession, seed_queued_job):
        result = await schedule_next_job(db)
        assert result is None

    @pytest.mark.asyncio
    async def test_schedule_rejects_stale_online_node(self, db: AsyncSession, seed_queued_job, seed_node):
        seed_node.last_heartbeat = datetime.now(timezone.utc) - timedelta(minutes=10)
        await db.flush()

        assert await schedule_next_job(db) is None
