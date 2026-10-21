"""Canonical worker API router (lease-scoped).

PRD v3.1 §16 canonical worker routes:

  POST /v1/worker/leases/next
    — Returns only confirmed active leases. Never returns pending_chain.
    — Creates new pending_chain leases via scheduler if eligible jobs exist.

  POST /v1/worker/leases/{lease_id}/ack
    — Requires an active lease owned by authenticated node.
    — Transitions DB workflow to running.
    — Does NOT perform or replace on-chain assignment.

  POST /v1/worker/leases/{lease_id}/result-upload
    — Requires active lease, verifies node ownership.

  POST /v1/worker/leases/{lease_id}/complete
    — Requires active lease, verifies node ownership.

  POST /v1/worker/leases/{lease_id}/fail
    — Requires active or pending_chain lease, verifies node ownership.

  POST /v1/worker/nodes/{node_id}/heartbeat
    — Verifies authenticated node matches node_id.

All routes authenticate via X-API-Key and verify node owns the referenced lease.
"""

import base64
import binascii
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Job, JobAttempt, Lease, Node, Proof, SupportedModel, User
from app.runtime import get_storage
from app.services.job_service import update_job_status
from app.services.node_service import get_node_by_api_key_hash, update_heartbeat
from app.services.retry_policy import apply_attempt_failure, reconcile_expired_leases
from app.services.scheduler import schedule_next_job
from app.services.storage import StorageBackend, StorageUnavailableError, make_result_key
from app.utils import uuid_to_bytes32

router = APIRouter()


# ── Auth ────────────────────────────────────────────────────────


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


async def _authenticate_worker(
    x_api_key: str = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Node:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    api_key_hash = _hash_api_key(x_api_key)
    node = await get_node_by_api_key_hash(db, api_key_hash)
    if not node:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return node


async def _get_lease_and_verify_node(
    lease_id: str,
    node: Node,
    db: AsyncSession,
) -> Lease:
    """Fetch lease and verify the node owns it."""
    try:
        lid = uuid.UUID(lease_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid lease ID format")

    result = await db.execute(select(Lease).where(Lease.id == lid))
    lease = result.scalar_one_or_none()
    if not lease:
        raise HTTPException(status_code=404, detail="Lease not found")
    if lease.node_id != node.id:
        raise HTTPException(status_code=403, detail="Lease does not belong to this node")
    return lease


# ── Schemas ─────────────────────────────────────────────────────


class LeaseNextResponse(BaseModel):
    lease: dict | None = None


class AckRequest(BaseModel):
    worker_signer_address: str | None = None


class AckResponse(BaseModel):
    lease_id: str
    status: str
    job: dict


class ResultUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_file_key: str
    result_bytes_base64: str


Hash32 = Annotated[str, Field(pattern=r"^0x[0-9a-fA-F]{64}$")]


class CompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: int
    chain_id: int
    verifying_contract: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
    job_id: Hash32
    attempt_id: Hash32
    lease_id: Hash32
    provider: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
    fingerprint: Hash32
    merkle_root: Hash32
    output_hash: Hash32
    proof_timestamp: int
    lease_expires_at: int
    checkpoint_names: list[str] = Field(min_length=1, max_length=32)
    trace_hashes: list[Hash32] = Field(min_length=1, max_length=32)
    signature: str = Field(pattern=r"^0x[0-9a-fA-F]{130}$")
    result_file_key: str


class CompleteResponse(BaseModel):
    lease_id: str
    status: str


class FailRequest(BaseModel):
    error: str | None = None


class FailResponse(BaseModel):
    lease_id: str
    status: str


class HeartbeatResponse(BaseModel):
    detail: str


# ── Routes ──────────────────────────────────────────────────────


@router.post("/leases/next", response_model=LeaseNextResponse)
async def worker_lease_next(
    node: Node = Depends(_authenticate_worker),
    db: AsyncSession = Depends(get_db),
):
    """Worker polls for the next available active lease assigned to this node.

    PRD v3.1: Returns only confirmed active leases. Never returns pending_chain.
    The backend dispatcher must have already activated the lease on-chain.
    If no active lease exists, the scheduler may create a new pending_chain lease
    (which will need dispatcher activation before the worker can see it).
    """
    await reconcile_expired_leases(db)

    # Check for existing active leases assigned to this node
    active_result = await db.execute(
        select(Lease)
        .join(Job, Lease.job_id == Job.id)
        .where(
            Lease.node_id == node.id,
            Lease.status == "active",
            Job.status.notin_(["verifying", "settling", "completed", "refunded"]),
        )
    )
    active_lease = active_result.scalar_one_or_none()

    if active_lease:
        result = await db.execute(select(Job).where(Job.id == active_lease.job_id))
        job = result.scalar_one()
        attempt = (await db.execute(select(JobAttempt).where(JobAttempt.lease_id == active_lease.id))).scalar_one()
        provider = (await db.execute(select(User).where(User.id == node.provider_id))).scalar_one()
        model = (await db.execute(select(SupportedModel).where(SupportedModel.id == job.model_id))).scalar_one()
        return LeaseNextResponse(
            lease={
                "lease_id": str(active_lease.id),
                "lease_id_chain": active_lease.lease_id,
                "job_id": str(job.id),
                "chain_job_id": job.chain_job_id,
                "model_id": job.model_id,
                "input_file_key": job.input_file_key,
                "input_hash": job.input_hash,
                "attempt_id": str(attempt.id),
                "provider": provider.wallet_address,
                "expected_fingerprint": job.expected_fingerprint,
                "model_hash": model.model_hash_sha256,
                "model_version": model.model_version,
                "preprocessing_version": model.preprocessing_version,
                "lease_expires_at": active_lease.expires_at.isoformat(),
            }
        )

    # No active lease — try to schedule a new job (creates pending_chain lease)
    result = await schedule_next_job(db)
    if not result:
        return LeaseNextResponse(lease=None)

    job, assigned_node, lease = result
    if assigned_node.id != node.id:
        return LeaseNextResponse(lease=None)

    # The lease is pending_chain — return None (dispatcher must activate first)
    # UNLESS the lease was already activated (e.g., in test setup)
    if lease.status != "active":
        return LeaseNextResponse(lease=None)

    return LeaseNextResponse(
        lease={
            "lease_id": str(lease.id),
            "job_id": str(job.id),
            "chain_job_id": job.chain_job_id,
            "model_id": job.model_id,
            "input_file_key": job.input_file_key,
            "input_hash": job.input_hash,
            "lease_expires_at": lease.expires_at.isoformat(),
        }
    )


@router.post("/leases/{lease_id}/ack", response_model=AckResponse)
async def worker_lease_ack(
    lease_id: str,
    req: AckRequest,
    node: Node = Depends(_authenticate_worker),
    db: AsyncSession = Depends(get_db),
):
    """Worker acknowledges an active lease and transitions workflow to running.

    PRD v3.1: This endpoint does NOT perform or replace on-chain assignment.
    The lease must already be in 'active' status (confirmed by backend dispatcher).
    Only active/assigned leases may be acknowledged.
    """
    lease = await _get_lease_and_verify_node(lease_id, node, db)

    if lease.status != "active":
        raise HTTPException(
            status_code=409,
            detail=f"Lease status is {lease.status}, expected active",
        )

    # Fetch the associated job
    result = await db.execute(select(Job).where(Job.id == lease.job_id))
    job = result.scalar_one()
    if job.current_lease_id != lease.id:
        raise HTTPException(status_code=409, detail="Lease is no longer current")

    if req.worker_signer_address and node.worker_signer_address:
        if req.worker_signer_address.lower() != node.worker_signer_address.lower():
            raise HTTPException(status_code=409, detail="Worker signer does not match registered node signer")

    # Exact repeated acknowledgements are idempotent.
    if job.status in ("assigned", "active"):
        await update_job_status(db, job.id, "running")
        job.started_at = datetime.now(timezone.utc)
        node.active_leases = (node.active_leases or 0) + 1
    elif job.status != "running":
        raise HTTPException(status_code=409, detail=f"Job status is {job.status}, expected assigned or running")

    # Store worker signer address if provided
    if req.worker_signer_address and not node.worker_signer_address:
        node.worker_signer_address = req.worker_signer_address

    await db.flush()

    return AckResponse(
        lease_id=str(lease.id),
        status="active",
        job={
            "id": str(job.id),
            "chain_job_id": job.chain_job_id,
            "model_id": job.model_id,
            "input_file_key": job.input_file_key,
            "input_hash": job.input_hash,
        },
    )


@router.post("/leases/{lease_id}/result-upload")
async def worker_result_upload(
    lease_id: str,
    req: ResultUploadRequest,
    node: Node = Depends(_authenticate_worker),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    """Worker uploads result file reference and output hash."""
    lease = await _get_lease_and_verify_node(lease_id, node, db)

    if lease.status != "active":
        raise HTTPException(status_code=409, detail=f"Lease status is {lease.status}, expected active")

    result = await db.execute(select(Job).where(Job.id == lease.job_id))
    job = result.scalar_one()
    if job.current_lease_id != lease.id:
        raise HTTPException(status_code=409, detail="Lease is no longer current")
    attempt_result = await db.execute(select(JobAttempt).where(JobAttempt.lease_id == lease.id))
    attempt = attempt_result.scalar_one()
    expected_key = make_result_key(str(job.id), str(attempt.id))
    if req.result_file_key != expected_key:
        raise HTTPException(status_code=422, detail="Result key is not owned by this job attempt")
    try:
        result_bytes = base64.b64decode(req.result_bytes_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail="Invalid base64 result bytes") from exc
    if len(result_bytes) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Result exceeds maximum size")
    output_hash = hashlib.sha256(result_bytes).hexdigest()
    if job.result_output_hash:
        if job.result_output_hash != output_hash or job.result_file_key != expected_key:
            raise HTTPException(status_code=409, detail="A different result already exists for this attempt")
    await db.commit()
    try:
        await storage.put_object_once(expected_key, result_bytes, "application/octet-stream")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Result storage unavailable") from exc
    lease = (
        await db.execute(
            select(Lease).where(Lease.id == lease.id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one()
    if lease.status != "active":
        raise HTTPException(status_code=409, detail="Lease is no longer active")
    job = (
        await db.execute(
            select(Job).where(Job.id == lease.job_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one()
    if job.current_lease_id != lease.id:
        raise HTTPException(status_code=409, detail="Lease is no longer current")
    job.result_file_key = req.result_file_key
    job.result_output_hash = output_hash
    job.result_size_bytes = len(result_bytes)

    await db.flush()
    return {"detail": "Result uploaded"}


@router.post("/leases/{lease_id}/complete", response_model=CompleteResponse, status_code=202)
async def worker_lease_complete(
    lease_id: str,
    req: CompleteRequest,
    node: Node = Depends(_authenticate_worker),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    """Persist a complete proof envelope for asynchronous verification."""
    lease = await _get_lease_and_verify_node(lease_id, node, db)

    if lease.status != "active":
        raise HTTPException(status_code=409, detail=f"Lease status is {lease.status}, expected active")

    result = await db.execute(select(Job).where(Job.id == lease.job_id))
    job = result.scalar_one()
    if job.current_lease_id != lease.id:
        raise HTTPException(status_code=409, detail="Lease is no longer current")
    attempt_result = await db.execute(select(JobAttempt).where(JobAttempt.lease_id == lease.id))
    attempt = attempt_result.scalar_one()
    provider_result = await db.execute(select(User).where(User.id == node.provider_id))
    provider = provider_result.scalar_one()
    expected = {
        "job_id": job.chain_job_id.lower(),
        "attempt_id": uuid_to_bytes32(attempt.id).lower(),
        "lease_id": lease.lease_id.lower(),
        "provider": provider.wallet_address.lower(),
        "fingerprint": "0x" + (job.expected_fingerprint or "").removeprefix("0x").lower(),
        "lease_expires_at": int(lease.expires_at.timestamp()),
    }
    actual = {
        "job_id": req.job_id.lower(),
        "attempt_id": req.attempt_id.lower(),
        "lease_id": req.lease_id.lower(),
        "provider": req.provider.lower(),
        "fingerprint": req.fingerprint.lower(),
        "lease_expires_at": req.lease_expires_at,
    }
    if actual != expected:
        raise HTTPException(status_code=409, detail="Proof envelope binding does not match current assignment")
    if req.protocol_version != 1:
        raise HTTPException(status_code=422, detail="Unsupported proof protocol version")
    if req.chain_id != settings.CHAIN_ID or req.verifying_contract.lower() != settings.NEBULA_PAYMENT_CONTRACT.lower():
        raise HTTPException(status_code=409, detail="Proof domain does not match configured chain and contract")
    if req.proof_timestamp > int(lease.expires_at.timestamp()) or req.proof_timestamp > int(job.deadline.timestamp()):
        raise HTTPException(status_code=409, detail="Proof timestamp exceeds lease or job deadline")
    if int(req.merkle_root, 16) == 0 or int(req.output_hash, 16) == 0:
        raise HTTPException(status_code=422, detail="Contract proof hashes must be non-zero")
    if req.result_file_key != make_result_key(str(job.id), str(attempt.id)):
        raise HTTPException(status_code=422, detail="Result key is not owned by this job attempt")
    await db.commit()
    try:
        result_bytes = await storage.get_object(req.result_file_key)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail="Result object does not exist") from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Result storage unavailable") from exc
    if len(result_bytes) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Result exceeds maximum size")
    lease = (
        await db.execute(
            select(Lease).where(Lease.id == lease.id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one()
    if lease.status != "active":
        raise HTTPException(status_code=409, detail="Lease is no longer active")
    job = (
        await db.execute(
            select(Job).where(Job.id == lease.job_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one()
    if job.current_lease_id != lease.id:
        raise HTTPException(status_code=409, detail="Lease is no longer current")
    attempt = (await db.execute(select(JobAttempt).where(JobAttempt.lease_id == lease.id))).scalar_one()
    output_hash = hashlib.sha256(result_bytes).hexdigest()
    if req.output_hash[2:].lower() != output_hash:
        raise HTTPException(status_code=422, detail="Result bytes do not match proof output hash")
    existing_result = await db.execute(select(Proof).where(Proof.job_attempt_id == attempt.id))
    existing = existing_result.scalar_one_or_none()
    if existing:
        if existing.envelope != req.model_dump():
            raise HTTPException(status_code=409, detail="A different proof already exists for this attempt")
        return CompleteResponse(lease_id=str(lease.id), status="verification_queued")

    proof = Proof(
        id=uuid.uuid4(),
        job_attempt_id=attempt.id,
        protocol_version=req.protocol_version,
        fingerprint_hash=req.fingerprint[2:].lower(),
        merkle_root=req.merkle_root.lower(),
        output_hash=req.output_hash[2:].lower(),
        signature=req.signature.lower(),
        signer_address=node.worker_signer_address or "",
        trace_hashes=req.trace_hashes,
        proof_timestamp=datetime.fromtimestamp(req.proof_timestamp, timezone.utc),
        envelope=req.model_dump(),
    )
    db.add(proof)
    job.status = "verifying"
    job.result_output_hash = output_hash
    job.result_size_bytes = len(result_bytes)
    await db.flush()

    return CompleteResponse(lease_id=str(lease.id), status="verification_queued")


@router.get("/leases/{lease_id}/input")
async def worker_lease_input(
    lease_id: str,
    node: Node = Depends(_authenticate_worker),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    lease = await _get_lease_and_verify_node(lease_id, node, db)
    if lease.status != "active":
        raise HTTPException(status_code=409, detail="Lease is not active")
    job = (await db.execute(select(Job).where(Job.id == lease.job_id))).scalar_one()
    if job.current_lease_id != lease.id:
        raise HTTPException(status_code=409, detail="Lease is no longer current")
    if not job.input_file_key:
        raise HTTPException(status_code=404, detail="Input object is not configured")
    try:
        await db.commit()
        data = await storage.get_object(job.input_file_key)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Input object not found") from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Input storage unavailable") from exc
    lease = (
        await db.execute(select(Lease).where(Lease.id == lease.id).execution_options(populate_existing=True))
    ).scalar_one()
    job = (
        await db.execute(select(Job).where(Job.id == lease.job_id).execution_options(populate_existing=True))
    ).scalar_one()
    if lease.status != "active" or job.current_lease_id != lease.id:
        raise HTTPException(status_code=409, detail="Lease is no longer active and current")
    return Response(data, media_type="application/octet-stream")


@router.get("/leases/{lease_id}/model")
async def worker_lease_model(
    lease_id: str,
    node: Node = Depends(_authenticate_worker),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    lease = await _get_lease_and_verify_node(lease_id, node, db)
    if lease.status != "active":
        raise HTTPException(status_code=409, detail="Lease is not active")
    job = (await db.execute(select(Job).where(Job.id == lease.job_id))).scalar_one()
    if job.current_lease_id != lease.id:
        raise HTTPException(status_code=409, detail="Lease is no longer current")
    model = (await db.execute(select(SupportedModel).where(SupportedModel.id == job.model_id))).scalar_one_or_none()
    if not model or not model.model_source_url:
        raise HTTPException(status_code=404, detail="Model artifact is not configured")
    try:
        await db.commit()
        data = await storage.get_object(model.model_source_url)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Model artifact not found") from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Model storage unavailable") from exc
    lease = (
        await db.execute(select(Lease).where(Lease.id == lease.id).execution_options(populate_existing=True))
    ).scalar_one()
    job = (
        await db.execute(select(Job).where(Job.id == lease.job_id).execution_options(populate_existing=True))
    ).scalar_one()
    if lease.status != "active" or job.current_lease_id != lease.id:
        raise HTTPException(status_code=409, detail="Lease is no longer active and current")
    return Response(data, media_type="application/octet-stream")


@router.post("/leases/{lease_id}/fail", response_model=FailResponse)
async def worker_lease_fail(
    lease_id: str,
    req: FailRequest,
    node: Node = Depends(_authenticate_worker),
    db: AsyncSession = Depends(get_db),
):
    """Worker marks lease as failed."""
    lease = await _get_lease_and_verify_node(lease_id, node, db)

    if lease.status not in ("active", "pending_chain"):
        raise HTTPException(status_code=409, detail=f"Lease status is {lease.status}")

    job = (await db.execute(select(Job).where(Job.id == lease.job_id))).scalar_one()
    if job.status in ("verifying", "completed", "refunded"):
        return FailResponse(lease_id=str(lease.id), status="verification_queued")

    await apply_attempt_failure(db, lease, reason=req.error or "worker failure")
    await db.flush()

    return FailResponse(lease_id=str(lease.id), status="failed")


@router.post("/nodes/{node_id}/heartbeat", response_model=HeartbeatResponse)
async def worker_node_heartbeat(
    node_id: str,
    node: Node = Depends(_authenticate_worker),
    db: AsyncSession = Depends(get_db),
):
    """Node heartbeat. Verifies the authenticated node matches node_id."""
    try:
        nid = uuid.UUID(node_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid node ID format")

    if nid != node.id:
        raise HTTPException(status_code=403, detail="Node ID does not match authenticated node")

    if node.status == "pending":
        node.status = "online"
    await update_heartbeat(db, node)
    return HeartbeatResponse(detail="Heartbeat recorded")
