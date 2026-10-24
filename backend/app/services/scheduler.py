"""Scheduler service: match queued jobs to available nodes.

PRD v3.1 §13: Scheduler matches queued jobs to online nodes with sufficient VRAM.
Uses FOR UPDATE SKIP LOCKED on PostgreSQL for concurrent scheduler safety.
Falls back to regular SELECT on SQLite.

The scheduler creates pending_chain leases. The backend dispatcher
(submitting assignProvider() on-chain) transitions them to active.
The worker routes activate pending_chain leases via the dispatcher
before returning them to the worker.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ChainTransaction, Job, Lease, Node, SupportedModel
from app.services.lease_service import create_lease


async def _lock_next_queued_job(db: AsyncSession) -> uuid.UUID | None:
    """Lock the oldest eligible job, retaining confirmed leases until strict expiry."""
    dialect = db.bind.dialect.name if db.bind else "sqlite"
    query = (
        "SELECT id FROM jobs "
        "WHERE status IN ('queued', 'retry_pending') "
        "AND NOT EXISTS (SELECT 1 FROM leases WHERE leases.job_id = jobs.id "
        "AND leases.status IN ('active','pending_chain')) "
        # A worker failure closes the local attempt, but cannot shorten its
        # confirmed on-chain lease. Reassignment at the exact expiry also
        # reverts, so keep blocked retries out of the candidate selection.
        "AND NOT EXISTS (SELECT 1 FROM leases previous "
        "JOIN chain_transactions assignment ON assignment.lease_id = previous.id "
        "WHERE previous.job_id = jobs.id AND previous.expires_at >= :now "
        "AND assignment.tx_type = 'assignProvider' "
        "AND assignment.status IN ('confirmed','finalized')) "
        "ORDER BY created_at ASC LIMIT 1"
    )
    if dialect == "postgresql":
        query += " FOR UPDATE SKIP LOCKED"
    result = await db.execute(
        text(query).bindparams(bindparam("now", type_=DateTime(timezone=True))),
        {"now": datetime.now(timezone.utc)},
    )

    row = result.first()
    if not row:
        return None
    val = row[0]
    return uuid.UUID(val) if isinstance(val, str) else val


async def schedule_next_job(
    db: AsyncSession,
) -> tuple[Job, Node, Lease] | None:
    """Find next queued/retry_pending job and assign it to an available online node.

    Uses FOR UPDATE SKIP LOCKED on PostgreSQL for concurrent scheduler safety.
    Creates a pending_chain lease. The lease is NOT yet active — the backend
    dispatcher must submit assignProvider() on-chain and confirm the
    ProviderAssigned event before the lease becomes active and worker-dispatchable.

    Returns (job, node, lease) or None if no match.
    """
    job_id = await _lock_next_queued_job(db)
    if not job_id:
        return None

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()

    # Reject if already has an active/pending_chain lease
    existing_lease = await db.execute(
        select(Lease).where(
            Lease.job_id == job.id,
            Lease.status.in_(["active", "pending_chain"]),
        )
    )
    if existing_lease.scalar_one_or_none():
        return None

    # Get the model to check VRAM requirements
    model_result = await db.execute(select(SupportedModel).where(SupportedModel.id == job.model_id))
    model = model_result.scalar_one_or_none()
    required_vram = model.vram_required_gb if model else 0

    # Find an online node with sufficient VRAM and lowest active leases
    node_result = await db.execute(
        select(Node)
        .where(
            Node.status == "online",
            Node.vram_gb >= required_vram,
            Node.last_heartbeat >= datetime.now(timezone.utc) - timedelta(seconds=settings.NODE_HEARTBEAT_TTL_SECONDS),
        )
        .order_by(Node.active_leases.asc(), Node.last_heartbeat.desc())
        .limit(1)
    )
    node = node_result.scalar_one_or_none()
    if not node:
        return None

    # Create lease in pending_chain status
    lease = await create_lease(
        db,
        job_id=job.id,
        node_id=node.id,
        lease_duration_minutes=60,
    )

    # Create attempt record
    job.current_attempt += 1
    from app.models import JobAttempt

    attempt = JobAttempt(
        id=uuid.uuid4(),
        job_id=job.id,
        node_id=node.id,
        lease_id=lease.id,
        attempt_number=job.current_attempt,
        status="running",
    )
    db.add(attempt)

    # Persist the unique transaction intent in the same transaction. The job
    # remains queued/retry_pending until a matching ProviderAssigned receipt is
    # observed; pending_chain is never worker-dispatchable.
    intent = ChainTransaction(
        id=uuid.uuid4(),
        chain_id=settings.CHAIN_ID,
        contract_address=settings.NEBULA_PAYMENT_CONTRACT or "0x" + "00" * 20,
        job_id=job.id,
        lease_id=lease.id,
        tx_type="assignProvider",
        from_address=settings.BACKEND_EXECUTOR_ADDRESS or "0x" + "00" * 20,
        to_address=settings.NEBULA_PAYMENT_CONTRACT or "0x" + "00" * 20,
        idempotency_key=f"assignProvider:{lease.id}",
        status="pending",
    )
    db.add(intent)
    job.assigned_node_id = node.id
    job.current_lease_id = lease.id

    await db.flush()
    return job, node, lease
