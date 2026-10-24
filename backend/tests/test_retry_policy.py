"""Retry, exhaustion, reassignment, and stale-worker integration tests."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models import ChainTransaction, Job, JobAttempt, Lease, Node, SupportedModel, User
from app.services.retry_policy import apply_attempt_failure, reconcile_expired_leases
from app.services.scheduler import schedule_next_job
from app.utils import uuid_to_bytes32


async def _seed_expiring_attempt(db, *, attempt_number: int, deadline: datetime):
    user = User(id=uuid.uuid4(), wallet_address="0x" + "11" * 20, role="user")
    old_provider = User(id=uuid.uuid4(), wallet_address="0x" + "22" * 20, role="provider")
    new_provider = User(id=uuid.uuid4(), wallet_address="0x" + "33" * 20, role="provider")
    model = SupportedModel(id="retry-model", name="Retry", price_base_units=50_000, vram_required_gb=1)
    old_key = "old-worker-key"
    old_node = Node(
        id=uuid.uuid4(),
        provider_id=old_provider.id,
        status="online",
        vram_gb=8,
        api_key_hash=hashlib.sha256(old_key.encode()).hexdigest(),
        worker_signer_address="0x" + "44" * 20,
        active_leases=1,
        last_heartbeat=datetime.now(timezone.utc),
    )
    new_node = Node(
        id=uuid.uuid4(),
        provider_id=new_provider.id,
        status="online",
        vram_gb=8,
        api_key_hash=hashlib.sha256(b"new-worker-key").hexdigest(),
        worker_signer_address="0x" + "55" * 20,
        active_leases=0,
        last_heartbeat=datetime.now(timezone.utc),
    )
    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        user_id=user.id,
        model_id=model.id,
        chain_job_id=uuid_to_bytes32(job_id),
        assigned_node_id=old_node.id,
        status="running",
        price_base_units=50_000,
        deadline=deadline,
        max_attempts=3,
        current_attempt=attempt_number,
    )
    lease = Lease(
        id=uuid.uuid4(),
        job_id=job.id,
        node_id=old_node.id,
        lease_id="0x" + "66" * 32,
        status="active",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    attempt = JobAttempt(
        id=uuid.uuid4(),
        job_id=job.id,
        node_id=old_node.id,
        lease_id=lease.id,
        attempt_number=attempt_number,
        status="running",
    )
    job.current_lease_id = lease.id
    db.add_all([user, old_provider, new_provider, model, old_node, new_node, job, lease, attempt])
    await db.commit()
    return job, lease, attempt, old_node, new_node, old_key


@pytest.mark.asyncio
async def test_expired_lease_reassigns_and_old_worker_is_rejected(db):
    job, old_lease, old_attempt, old_node, new_node, old_key = await _seed_expiring_attempt(
        db,
        attempt_number=1,
        deadline=datetime.now(timezone.utc) + timedelta(hours=3),
    )

    result = await reconcile_expired_leases(db)
    assert result == {"expired": 1, "awaiting_timeout_refund": 0}
    assert job.status == "retry_pending"
    assert old_lease.status == "expired"
    assert old_attempt.status == "expired"
    assert old_attempt.error == "lease expired"
    assert old_attempt.completed_at is not None
    assert old_node.active_leases == 0

    old_node.status = "offline"
    reassigned = await schedule_next_job(db)
    assert reassigned is not None
    reassigned_job, selected_node, new_lease = reassigned
    assert reassigned_job.id == job.id
    assert selected_node.id == new_node.id
    assert new_lease.id != old_lease.id
    assert new_lease.status == "pending_chain"
    assert job.current_attempt == 2
    new_attempt = (await db.execute(select(JobAttempt).where(JobAttempt.lease_id == new_lease.id))).scalar_one()
    assert new_attempt.attempt_number == 2

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        stale_ack = await client.post(
            f"/v1/worker/leases/{old_lease.id}/ack",
            headers={"X-API-Key": old_key},
            json={},
        )
    assert stale_ack.status_code == 409


@pytest.mark.asyncio
async def test_third_expired_attempt_advances_to_timeout_refund(db):
    job, lease, attempt, node, _, _ = await _seed_expiring_attempt(
        db,
        attempt_number=3,
        deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    result = await reconcile_expired_leases(db)

    assert result == {"expired": 1, "awaiting_timeout_refund": 1}
    assert job.status == "awaiting_timeout_refund"
    assert lease.status == "expired"
    assert attempt.status == "expired"
    assert node.active_leases == 0
    assert await schedule_next_job(db) is None


@pytest.mark.asyncio
async def test_expired_deadline_never_schedules_another_attempt(db):
    job, lease, attempt, node, _, _ = await _seed_expiring_attempt(
        db,
        attempt_number=1,
        deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    result = await reconcile_expired_leases(db)

    assert result == {"expired": 1, "awaiting_timeout_refund": 1}
    assert job.status == "awaiting_timeout_refund"
    assert lease.status == "expired"
    assert attempt.status == "expired"
    assert node.active_leases == 0
    assert await schedule_next_job(db) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("assignment_status", "seconds_until_expiry", "can_schedule"),
    [("confirmed", 1800, False), ("finalized", 0, False), ("confirmed", -1, True), ("reverted", 1800, True)],
)
async def test_worker_failure_waits_for_confirmed_on_chain_lease_expiry(
    db, assignment_status, seconds_until_expiry, can_schedule
):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    job, lease, _, _, _, _ = await _seed_expiring_attempt(
        db,
        attempt_number=1,
        deadline=datetime.now(timezone.utc) + timedelta(hours=3),
    )
    lease.expires_at = now + timedelta(seconds=seconds_until_expiry)
    db.add(
        ChainTransaction(
            job_id=job.id,
            lease_id=lease.id,
            chain_id=421614,
            contract_address="0x" + "77" * 20,
            tx_type="assignProvider",
            from_address="0x" + "88" * 20,
            to_address="0x" + "77" * 20,
            status=assignment_status,
        )
    )
    await apply_attempt_failure(db, lease, reason="worker process crashed")

    assert job.status == "retry_pending"
    with patch("app.services.scheduler.datetime") as clock:
        clock.now.return_value = now
        result = await schedule_next_job(db)
    assert (result is not None) is can_schedule
    assert job.current_attempt == (2 if can_schedule else 1)


@pytest.mark.asyncio
async def test_blocked_oldest_retry_does_not_starve_a_queued_job(db):
    now = datetime.now(timezone.utc)
    blocked, lease, _, _, _, _ = await _seed_expiring_attempt(
        db, attempt_number=1, deadline=now + timedelta(hours=3)
    )
    blocked.created_at = now - timedelta(hours=1)
    lease.expires_at = now + timedelta(minutes=30)
    db.add(
        ChainTransaction(
            job_id=blocked.id,
            lease_id=lease.id,
            chain_id=421614,
            contract_address="0x" + "77" * 20,
            tx_type="assignProvider",
            from_address="0x" + "88" * 20,
            to_address="0x" + "77" * 20,
            status="confirmed",
        )
    )
    await apply_attempt_failure(db, lease, reason="worker process crashed")
    ready_id = uuid.uuid4()
    ready = Job(
        id=ready_id,
        user_id=blocked.user_id,
        model_id=blocked.model_id,
        chain_job_id=uuid_to_bytes32(ready_id),
        status="queued",
        price_base_units=50_000,
        deadline=now + timedelta(hours=3),
        created_at=now,
    )
    db.add(ready)
    await db.flush()

    result = await schedule_next_job(db)

    assert result is not None
    assert result[0].id == ready.id
    assert blocked.current_attempt == 1


@pytest.mark.asyncio
async def test_active_lease_verification_failure_can_still_retry(db):
    job, lease, _, _, _, _ = await _seed_expiring_attempt(
        db, attempt_number=1, deadline=datetime.now(timezone.utc) + timedelta(hours=3)
    )
    job.status = "verifying"

    await apply_attempt_failure(db, lease, reason="Result object not found")

    assert job.status == "retry_pending"
    assert job.error_message == "Result object not found"
    assert lease.status == "failed"
