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


@pytest.mark.asyncio
async def test_two_providers_receive_exclusive_jobs_without_overbooking(
    db,
    seed_queued_job,
    seed_node,
    seed_model,
    seed_user,
):
    """A pending on-chain assignment already reserves its GPU node."""
    other_provider = User(wallet_address="0x" + "77" * 20, role="provider")
    db.add(other_provider)
    await db.flush()
    other_node = Node(
        provider_id=other_provider.id,
        gpu_name="RTX 5050",
        vram_gb=8,
        status="online",
        api_key_hash="ab" * 32,
        active_leases=0,
        last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    db.add(other_node)
    for _ in range(2):
        job = await create_job(
            db,
            user_id=seed_user.id,
            model_id=seed_model.id,
            chain_job_id="0x" + uuid.uuid4().hex,
            price_base_units=int(seed_model.price_base_units),
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        await confirm_job_escrow(
            db, job_id=job.id, tx_hash="0x" + uuid.uuid4().hex, escrow_amount=int(seed_model.price_base_units)
        )
    await db.flush()
    first = await schedule_next_job(db)
    second = await schedule_next_job(db)
    assert first is not None and second is not None
    assert {first[1].id, second[1].id} == {seed_node.id, other_node.id}
    assert first[0].id != second[0].id
    assert await schedule_next_job(db) is None


class TestScheduler:
    @pytest.mark.asyncio
    async def test_unavailable_bert_job_does_not_block_resnet(
        self, db, seed_queued_job, seed_node, seed_model, seed_user
    ):
        bert = SupportedModel(id="bert-base", name="BERT", price_base_units=50000, vram_required_gb=4)
        db.add(bert)
        await db.flush()
        seed_queued_job.model_id = bert.id
        resnet_job = await create_job(
            db,
            user_id=seed_user.id,
            model_id=seed_model.id,
            chain_job_id="0x" + uuid.uuid4().hex,
            price_base_units=int(seed_model.price_base_units),
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        await confirm_job_escrow(
            db, job_id=resnet_job.id, tx_hash="0x" + uuid.uuid4().hex, escrow_amount=int(seed_model.price_base_units)
        )
        assignment = await schedule_next_job(db)
        assert assignment is not None
        assert assignment[0].id == resnet_job.id

    @pytest.mark.asyncio
    async def test_bert_is_only_assigned_after_worker_advertises_support(
        self, db, seed_queued_job, seed_node, seed_model
    ):
        from httpx import ASGITransport, AsyncClient

        from app.main import app

        bert = SupportedModel(
            id="bert-base", name="BERT sentiment", vram_required_gb=4, price_base_units=50000, input_type="text"
        )
        db.add(bert)
        await db.flush()
        seed_queued_job.model_id = bert.id
        await db.flush()
        assert await schedule_next_job(db) is None
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            heartbeat = await client.post(
                f"/v1/worker/nodes/{seed_node.id}/heartbeat",
                headers={"X-API-Key": "test-key"},
                json={"supported_models": ["resnet50", "bert-base"]},
            )
        assert heartbeat.status_code == 200
        assignment = await schedule_next_job(db)
        assert assignment is not None
        assert assignment[1].id == seed_node.id

    @pytest.mark.asyncio
    async def test_only_assigned_worker_receives_private_model_url(self, db, seed_queued_job, seed_node, seed_model):
        from httpx import ASGITransport, AsyncClient

        from app.main import app
        from app.services.lease_service import activate_lease

        seed_model.model_source_url = "models/approved.safetensors"
        _, _, lease = await schedule_next_job(db)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            path = f"/v1/worker/leases/{lease.id}/model-url"
            assert (await client.get(path, headers={"X-API-Key": "test-key"})).status_code == 409
            await activate_lease(db, lease.id)
            assert (await client.get(path, headers={"X-API-Key": "wrong"})).status_code == 401
            response = await client.get(path, headers={"X-API-Key": "test-key"})
            lease.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await db.flush()
            expired = await client.get(path, headers={"X-API-Key": "test-key"})
        assert response.status_code == 200
        assert "models/approved.safetensors" in response.json()["url"]
        assert expired.status_code == 409

    @pytest.mark.asyncio
    async def test_private_model_url_respects_the_configured_capability_ttl(
        self, db, seed_queued_job, seed_node, seed_model
    ):
        from httpx import ASGITransport, AsyncClient

        from app.main import app
        from app.services.lease_service import activate_lease
        from app.services.storage import InMemoryStorage

        class BoundedCapabilityStorage(InMemoryStorage):
            async def generate_download_url(self, key: str, expires_in: int = 300) -> str:
                if expires_in > 300:
                    raise ValueError("capability expiry exceeds the configured bounded lifetime")
                return f"https://private.invalid/{key}?expires={expires_in}"

        seed_model.model_source_url = "models/bert-base/approved.safetensors"
        _, _, lease = await schedule_next_job(db)
        await activate_lease(db, lease.id)
        app.state.storage = BoundedCapabilityStorage()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/v1/worker/leases/{lease.id}/model-url",
                headers={"X-API-Key": "test-key"},
            )

        assert response.status_code == 200
        assert response.json()["url"].endswith("?expires=300")

    @pytest.mark.asyncio
    async def test_user_can_see_assigned_provider_without_node_credentials(self, db, seed_queued_job, seed_node):
        from httpx import ASGITransport, AsyncClient

        from app.main import app
        from tests.conftest import seed_authed_user

        owner_id, token = await seed_authed_user(db)
        seed_queued_job.user_id = owner_id
        await schedule_next_job(db)
        await db.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/v1/jobs/{seed_queued_job.id}", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["assigned_node_id"] == str(seed_node.id)
        assert payload["assigned_gpu_name"] == "RTX 4090"
        assert payload["assigned_provider_address"].startswith("0x")
        assert "api_key" not in response.text

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
