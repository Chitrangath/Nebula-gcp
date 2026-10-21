"""Job service: lifecycle, escrow confirmation, status transitions.

PRD v3.1 §10: State machine — None→Created→Assigned→ProofSubmitted→Settled/Refunded
Terminal states: Settled, Refunded
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job


async def create_job(
    db: AsyncSession,
    *,
    job_id: uuid.UUID | None = None,
    user_id: uuid.UUID,
    model_id: str,
    chain_job_id: str,
    price_base_units: int,
    deadline: datetime,
    max_attempts: int = 3,
) -> Job:
    """Create a new job in pending_blockchain status.

    Called after frontend upload and contract createJob event emission.
    """
    job = Job(
        id=job_id or uuid.uuid4(),
        user_id=user_id,
        model_id=model_id,
        chain_job_id=chain_job_id,
        price_base_units=price_base_units,
        deadline=deadline,
        max_attempts=max_attempts,
        current_attempt=0,
        status="pending_blockchain",
    )
    db.add(job)
    await db.flush()
    return job


async def confirm_job_escrow(
    db: AsyncSession,
    *,
    job_id: uuid.UUID,
    tx_hash: str,
    escrow_amount: int,
) -> Job:
    """Confirm escrow deposit on-chain. Transitions pending_blockchain → queued."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise ValueError("Job not found")
    if job.status != "pending_blockchain":
        raise ValueError(f"Job status is {job.status}, expected pending_blockchain")

    job.status = "queued"
    job.blockchain_tx_hash = tx_hash
    job.blockchain_escrow_amount = escrow_amount
    await db.flush()
    return job


async def get_job(db: AsyncSession, job_id: uuid.UUID) -> Job | None:
    """Fetch a job by ID."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    return result.scalar_one_or_none()


async def list_user_jobs(db: AsyncSession, user_id: uuid.UUID) -> list[Job]:
    """List all jobs for a user, ordered by creation date descending."""
    result = await db.execute(select(Job).where(Job.user_id == user_id).order_by(Job.created_at.desc()))
    return list(result.scalars().all())


async def update_job_status(
    db: AsyncSession,
    job_id: uuid.UUID,
    new_status: str,
) -> Job:
    """Update job status. Validates the transition is allowed."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise ValueError("Job not found")

    valid_transitions: dict[str, list[str]] = {
        "pending_blockchain": ["queued", "expired_pre_escrow"],
        "queued": ["assigned", "expired_pre_escrow"],
        "assigned": ["running", "retry_pending", "attempts_exhausted"],
        "running": ["proof_submitted", "retry_pending", "attempts_exhausted"],
        "proof_submitted": ["verifying", "retry_pending"],
        "verifying": ["settling", "retry_pending"],
        "settling": ["completed"],
        "completed": [],
        "retry_pending": ["assigned"],
        "attempts_exhausted": ["awaiting_timeout_refund"],
        "awaiting_timeout_refund": ["refunded"],
        "refunded": [],
        "expired_pre_escrow": [],
        "failed": [],
    }

    allowed = valid_transitions.get(job.status, [])
    if new_status not in allowed:
        raise ValueError(f"Invalid transition: {job.status} → {new_status}. Allowed: {allowed}")

    job.status = new_status
    await db.flush()
    return job
