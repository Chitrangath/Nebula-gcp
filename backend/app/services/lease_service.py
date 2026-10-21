"""Lease service: lifecycle, heartbeat, expiry, completion.

PRD v3.1 §10: Lease state machine:
  None → pending_chain → active → expired/completed/failed
  pending_chain: created by scheduler, awaiting on-chain assignProvider confirmation
  active: confirmed on-chain by ProviderAssigned event, worker can execute
  expired: lease timeout, no heartbeat
  completed: proof accepted
  failed: proof rejected or error
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lease


async def create_lease(
    db: AsyncSession,
    *,
    job_id: uuid.UUID,
    node_id: uuid.UUID,
    lease_duration_minutes: int = 60,
) -> Lease:
    """Create a new lease in pending_chain status.

    The lease starts as pending_chain. It transitions to active only
    after the backend dispatcher confirms assignProvider() on-chain.
    """
    lease_id = "0x" + secrets.token_hex(32)
    now = datetime.now(timezone.utc)

    lease = Lease(
        id=uuid.uuid4(),
        job_id=job_id,
        node_id=node_id,
        lease_id=lease_id,
        started_at=now,
        expires_at=now + timedelta(minutes=lease_duration_minutes),
        status="pending_chain",
    )
    db.add(lease)
    await db.flush()
    return lease


async def get_active_lease_for_job(db: AsyncSession, job_id: uuid.UUID) -> Lease | None:
    """Get the active lease for a job. Returns only confirmed active leases."""
    result = await db.execute(
        select(Lease).where(
            Lease.job_id == job_id,
            Lease.status == "active",
        )
    )
    return result.scalar_one_or_none()


async def get_lease(db: AsyncSession, lease_id: uuid.UUID) -> Lease | None:
    """Fetch a lease by ID."""
    result = await db.execute(select(Lease).where(Lease.id == lease_id))
    return result.scalar_one_or_none()


async def heartbeat_lease(db: AsyncSession, lease_id: uuid.UUID) -> Lease:
    """Update lease heartbeat timestamp."""
    lease = await get_lease(db, lease_id)
    if not lease:
        raise ValueError("Lease not found")
    lease.heartbeat_at = datetime.now(timezone.utc)
    await db.flush()
    return lease


async def activate_lease(db: AsyncSession, lease_id: uuid.UUID) -> Lease:
    """Transition lease from pending_chain to active.

    This should only be called after on-chain ProviderAssigned confirmation.
    """
    lease = await get_lease(db, lease_id)
    if not lease:
        raise ValueError("Lease not found")
    if lease.status != "pending_chain":
        raise ValueError(f"Cannot activate lease in status {lease.status}")
    lease.status = "active"
    lease.heartbeat_at = datetime.now(timezone.utc)
    await db.flush()
    return lease


async def complete_lease(db: AsyncSession, lease_id: uuid.UUID) -> Lease:
    """Transition lease to completed."""
    lease = await get_lease(db, lease_id)
    if not lease:
        raise ValueError("Lease not found")
    lease.status = "completed"
    await db.flush()
    return lease


async def fail_lease(db: AsyncSession, lease_id: uuid.UUID) -> Lease:
    """Transition lease to failed."""
    lease = await get_lease(db, lease_id)
    if not lease:
        raise ValueError("Lease not found")
    lease.status = "failed"
    await db.flush()
    return lease


async def expire_overdue_leases(db: AsyncSession) -> int:
    """Expire all active/pending_chain leases past their deadline.

    Returns the number of expired leases.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Lease).where(
            Lease.status.in_(["active", "pending_chain"]),
            Lease.expires_at < now,
        )
    )
    leases = result.scalars().all()
    count = 0
    for lease in leases:
        lease.status = "expired"
        count += 1
    if leases:
        await db.flush()
    return count
