"""Lease failure/expiry policy and bounded-attempt recovery transitions."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, JobAttempt, Lease, Node


async def apply_attempt_failure(db: AsyncSession, lease: Lease, *, reason: str, status: str = "failed") -> Job:
    """Close one attempt and choose retry versus timeout-refund recovery."""
    job = (await db.execute(select(Job).where(Job.id == lease.job_id))).scalar_one()
    attempt = (await db.execute(select(JobAttempt).where(JobAttempt.lease_id == lease.id))).scalar_one_or_none()
    node = (await db.execute(select(Node).where(Node.id == lease.node_id))).scalar_one_or_none()
    was_active = lease.status == "active"
    was_pending = lease.status == "pending_chain"
    lease.status = status
    if attempt:
        attempt.status = "expired" if status == "expired" else "failed"
        attempt.error = reason
        attempt.completed_at = datetime.now(timezone.utc)
    if node and was_active:
        node.active_leases = max(0, (node.active_leases or 1) - 1)
    # A late failed assignment cannot undo proof processing or a terminal
    # outcome. Active-lease proof verification failures can still retry.
    protected_statuses = (
        "settling", "completed", "refunded", "failed", "expired_pre_escrow", "awaiting_timeout_refund"
    )
    if job.status in protected_statuses or (was_pending and job.status in ("proof_submitted", "verifying")):
        await db.flush()
        return job
    if job.deadline.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        job.status = "awaiting_timeout_refund"
    elif int(job.current_attempt or 0) >= int(job.max_attempts or 3):
        job.status = "attempts_exhausted"
    else:
        job.status = "retry_pending"
    job.error_message = reason
    await db.flush()
    return job


async def reconcile_expired_leases(db: AsyncSession) -> dict[str, int]:
    """Expire overdue leases and advance exhausted jobs toward user timeout recovery."""
    now = datetime.now(timezone.utc)
    rows = await db.execute(
        select(Lease).where(
            Lease.status.in_(["active", "pending_chain"]),
            Lease.expires_at < now,
        )
    )
    expired = 0
    awaiting_job_ids = set()
    for lease in rows.scalars().all():
        job = await apply_attempt_failure(db, lease, reason="lease expired", status="expired")
        if job.status == "awaiting_timeout_refund":
            awaiting_job_ids.add(job.id)
        expired += 1
    awaiting = await db.execute(
        select(Job).where(
            Job.status == "attempts_exhausted",
            Job.deadline < now,
        )
    )
    for job in awaiting.scalars().all():
        job.status = "awaiting_timeout_refund"
        awaiting_job_ids.add(job.id)
    awaiting_count = len(awaiting_job_ids)
    await db.flush()
    return {"expired": expired, "awaiting_timeout_refund": awaiting_count}
