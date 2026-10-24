import hashlib
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Response, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import (
    BlockchainEvent,
    ChainCursor,
    ChainTransaction,
    Job,
    JobAttempt,
    Lease,
    Node,
    Payment,
    Proof,
    ReconciliationIncident,
    SupportedModel,
    User,
)
from app.runtime import get_blockchain, get_storage
from app.security import get_current_user
from app.services.blockchain_service import BlockchainBackend
from app.services.escrow_confirmation import EscrowReceiptError, confirm_escrow_receipt
from app.services.fingerprint import compute_fingerprint
from app.services.job_service import (
    create_job,
    get_job,
    list_user_jobs,
)
from app.services.storage import StorageBackend, StorageUnavailableError
from app.utils import uuid_to_bytes32

router = APIRouter()
logger = logging.getLogger(__name__)


async def _cleanup_created_input(storage: StorageBackend, key: str, *, created: bool) -> None:
    """Best-effort cleanup that never deletes an object owned by another write."""
    if not created:
        return
    try:
        await storage.delete_object(key)
    except (OSError, StorageUnavailableError):
        logger.exception("Compensating input-object cleanup failed")


class ChainTransactionEvidence(BaseModel):
    hash: str
    status: str
    chain_id: int
    block_number: int | None


class JobResponse(BaseModel):
    id: str
    chain_job_id: str
    model_id: str
    status: str
    price_base_units: str
    deadline: str
    fingerprint: str | None = None
    proof_fingerprint: str | None = None
    created_at: str
    chain_id: int
    on_chain_state: str | None = None
    attempt_count: int = 0
    current_lease_status: str | None = None
    proof_verification_status: str | None = None
    result_available: bool = False
    result_download_endpoint: str | None = None
    escrow_transaction: ChainTransactionEvidence | None = None
    assignment_transaction: ChainTransactionEvidence | None = None
    proof_transaction: ChainTransactionEvidence | None = None
    settlement_transaction: ChainTransactionEvidence | None = None
    refund_transaction: ChainTransactionEvidence | None = None
    refund_status: str | None = None
    provider_payment_credit_status: str | None = None
    reconciliation_health: str = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    assigned_node_id: str | None = None
    assigned_gpu_name: str | None = None
    assigned_provider_address: str | None = None


class ConfirmEscrowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tx_hash: str


class ConfirmEscrowResponse(BaseModel):
    id: str
    status: str
    blockchain_tx_hash: str
    blockchain_escrow_amount: str


class JobListResponse(BaseModel):
    jobs: list[JobResponse]


@router.post("", response_model=JobResponse)
async def create_new_job(
    model_id: str = Form(...),
    deadline: datetime = Form(...),
    input_file: UploadFile = File(...),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", min_length=1, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> JobResponse:
    """Create a job from one authenticated, bounded, server-validated input upload."""
    from app.services.input_upload import InputTooLargeError, InputUploadError, accept_image_upload, accept_text_upload

    model_result = await db.execute(select(SupportedModel).where(SupportedModel.id == model_id))
    model = model_result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")

    job_id = (
        uuid.uuid5(uuid.NAMESPACE_URL, f"nebula:job-upload:{user.id}:{idempotency_key}")
        if idempotency_key
        else uuid.uuid4()
    )
    chain_job_id = uuid_to_bytes32(job_id)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    try:
        accept_upload = (
            accept_text_upload if model.id == "bert-base" and model.input_type == "text" else accept_image_upload
        )
        accepted = await accept_upload(
            input_file,
            supported_formats=model.supported_formats or [],
            max_size_bytes=(model.max_input_size_mb or 0) * 1024 * 1024,
        )
    except InputTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except InputUploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    input_hash = hashlib.sha256(accepted.data).hexdigest()
    existing = await get_job(db, job_id)
    if existing is not None:
        if existing.model_id != model_id or existing.input_hash != input_hash:
            raise HTTPException(status_code=409, detail="Idempotency key was already used for a different job input")
        return _basic_job_response(existing)
    model_hash_value = (model.model_hash_sha256 or "").removeprefix("sha256:").removeprefix("0x")
    if len(model_hash_value) != 64 or any(c not in "0123456789abcdefABCDEF" for c in model_hash_value):
        raise HTTPException(status_code=422, detail="Model artifact hash is not configured")
    try:
        fingerprint = compute_fingerprint(
            job_id=str(job_id),
            model_id=model.id,
            model_version=model.model_version or "1.0",
            model_hash=model_hash_value,
            input_hash=input_hash,
            preprocessing_version=model.preprocessing_version or "1.0",
        ).hex()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job = await create_job(
        db,
        job_id=job_id,
        user_id=user.id,
        model_id=model_id,
        chain_job_id=chain_job_id,
        price_base_units=int(model.price_base_units),
        deadline=deadline,
    )
    job.input_hash = input_hash
    job.expected_fingerprint = fingerprint
    job.input_file_key = f"inputs/{job.id}/input.{accepted.extension}"
    input_created = False
    try:
        write_result = await storage.put_object_once(job.input_file_key, accepted.data, accepted.content_type)
        input_created = write_result.created
        await db.flush()
    except (OSError, StorageUnavailableError, ValueError) as exc:
        await _cleanup_created_input(storage, job.input_file_key, created=input_created)
        await db.delete(job)
        await db.flush()
        raise HTTPException(status_code=503, detail="Input storage unavailable") from exc
    try:
        # Commit here so storage cleanup can still be performed if persistence
        # fails; the request dependency's later commit is then a no-op.
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        winner = await get_job(db, job_id) if idempotency_key else None
        if winner is not None and winner.model_id == model_id and winner.input_hash == input_hash:
            return _basic_job_response(winner)
        await _cleanup_created_input(storage, job.input_file_key, created=input_created)
        raise HTTPException(status_code=409, detail="Concurrent job creation conflict") from exc
    except Exception as exc:
        await db.rollback()
        await _cleanup_created_input(storage, job.input_file_key, created=input_created)
        raise HTTPException(status_code=503, detail="Job persistence unavailable") from exc
    return _basic_job_response(job)


def _basic_job_response(job: Job) -> JobResponse:
    return JobResponse(
        id=str(job.id),
        chain_job_id=job.chain_job_id,
        model_id=job.model_id,
        status=job.status,
        price_base_units=str(job.price_base_units),
        deadline=job.deadline.isoformat(),
        fingerprint=job.expected_fingerprint,
        created_at=job.created_at.isoformat() if job.created_at else "",
        chain_id=settings.CHAIN_ID,
    )


@router.post("/{job_id}/confirm-escrow", response_model=ConfirmEscrowResponse)
async def confirm_escrow(
    job_id: str,
    req: ConfirmEscrowRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    blockchain: BlockchainBackend = Depends(get_blockchain),
):
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    job = await get_job(db, jid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your job")

    try:
        confirmed = await confirm_escrow_receipt(
            db,
            blockchain=blockchain,
            job=job,
            authenticated_wallet=user.wallet_address,
            tx_hash=req.tx_hash,
            expected_chain_id=settings.CHAIN_ID,
            expected_contract=settings.NEBULA_PAYMENT_CONTRACT,
            confirmations_required=settings.CONFIRMATION_DEPTH,
        )
    except EscrowReceiptError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return ConfirmEscrowResponse(
        id=str(confirmed.id),
        status=confirmed.status,
        blockchain_tx_hash=confirmed.blockchain_tx_hash or "",
        blockchain_escrow_amount=str(confirmed.blockchain_escrow_amount or 0),
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    jobs = await list_user_jobs(db, user.id)
    return JobListResponse(
        jobs=[
            JobResponse(
                id=str(j.id),
                chain_job_id=j.chain_job_id,
                model_id=j.model_id,
                status=j.status,
                price_base_units=str(j.price_base_units),
                deadline=j.deadline.isoformat(),
                fingerprint=j.expected_fingerprint,
                created_at=j.created_at.isoformat() if j.created_at else "",
                chain_id=settings.CHAIN_ID,
            )
            for j in jobs
        ]
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_single_job(
    job_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    job = await get_job(db, jid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your job")

    assigned_node = None
    assigned_provider = None
    if job.assigned_node_id:
        assigned_node = await db.get(Node, job.assigned_node_id)
        if assigned_node:
            assigned_provider = await db.get(User, assigned_node.provider_id)
    attempts = list(
        (await db.execute(select(JobAttempt).where(JobAttempt.job_id == job.id).order_by(JobAttempt.attempt_number)))
        .scalars()
        .all()
    )
    lease = None
    if job.current_lease_id:
        lease = (await db.execute(select(Lease).where(Lease.id == job.current_lease_id))).scalar_one_or_none()
    proof = None
    if attempts:
        proof = (await db.execute(select(Proof).where(Proof.job_attempt_id == attempts[-1].id))).scalar_one_or_none()
    configured_contract = settings.NEBULA_PAYMENT_CONTRACT.lower()
    txs = list(
        (
            await db.execute(
                select(ChainTransaction)
                .where(
                    ChainTransaction.job_id == job.id,
                    ChainTransaction.chain_id == settings.CHAIN_ID,
                    func.lower(ChainTransaction.contract_address) == configured_contract,
                )
                .order_by(ChainTransaction.created_at, ChainTransaction.id)
            )
        )
        .scalars()
        .all()
    )
    escrow_tx = next((value for value in reversed(txs) if value.tx_type == "createJob"), None)
    chain_instance_id = escrow_tx.chain_instance_id if escrow_tx else None
    if chain_instance_id is not None:
        txs = [value for value in txs if value.chain_instance_id == chain_instance_id]
        event_query = select(BlockchainEvent).where(
            BlockchainEvent.job_id == job.id,
            BlockchainEvent.chain_id == settings.CHAIN_ID,
            func.lower(BlockchainEvent.contract_address) == configured_contract,
            BlockchainEvent.chain_instance_id == chain_instance_id,
        )
        events = list((await db.execute(event_query)).scalars().all())
    else:
        txs = []
        events = []
    payments = list((await db.execute(select(Payment).where(Payment.job_id == job.id))).scalars().all())
    cursor = None
    incident = None
    if chain_instance_id is not None:
        cursor = (
            await db.execute(
                select(ChainCursor).where(
                    ChainCursor.chain_id == settings.CHAIN_ID,
                    ChainCursor.chain_instance_id == chain_instance_id,
                    func.lower(ChainCursor.contract_address) == configured_contract,
                )
            )
        ).scalar_one_or_none()
        incident = (
            await db.execute(
                select(ReconciliationIncident.id).where(
                    ReconciliationIncident.chain_id == settings.CHAIN_ID,
                    ReconciliationIncident.chain_instance_id == chain_instance_id,
                    func.lower(ReconciliationIncident.contract_address) == configured_contract,
                    ReconciliationIncident.status == "open",
                )
            )
        ).first()

    def tx(kind: str) -> ChainTransactionEvidence | None:
        item = next((value for value in reversed(txs) if value.tx_type == kind), None)
        return (
            ChainTransactionEvidence(
                hash=item.tx_hash,
                status=item.status,
                chain_id=item.chain_id,
                block_number=item.block_number,
            )
            if item and item.tx_hash
            else None
        )

    chain_state = None
    canonical_events = sorted(
        (event for event in events if event.confirmation_status in ("confirmed", "finalized")),
        key=lambda value: (value.block_number, value.log_index),
    )
    for event in canonical_events:
        if event.event_name == "JobCreated":
            chain_state = "Created"
        elif event.event_name == "ProviderAssigned":
            chain_state = "Assigned"
        elif event.event_name == "ProofSubmitted":
            chain_state = "ProofSubmitted"
        elif event.event_name == "JobSettled":
            chain_state = "Settled" if event.event_data.get("valid") else "Refunded"
        elif event.event_name == "TimeoutRefundCredited":
            chain_state = "Refunded"
    refund_payment = next((p for p in payments if p.payment_type == "user_refund"), None)
    refund_transaction = tx("requestTimeoutRefund")
    if refund_transaction is None and refund_payment and refund_payment.blockchain_tx_hash:
        refund_hash = refund_payment.blockchain_tx_hash.lower()
        refund_event = next(
            (event for event in reversed(canonical_events) if event.transaction_hash.lower() == refund_hash),
            None,
        )
        if refund_event is not None:
            refund_transaction = ChainTransactionEvidence(
                hash=refund_event.transaction_hash,
                status=refund_event.confirmation_status,
                chain_id=refund_event.chain_id,
                block_number=refund_event.block_number,
            )
    response = JobResponse(
        id=str(job.id),
        chain_job_id=job.chain_job_id,
        model_id=job.model_id,
        status=job.status,
        price_base_units=str(job.price_base_units),
        deadline=job.deadline.isoformat(),
        fingerprint=job.expected_fingerprint,
        created_at=job.created_at.isoformat() if job.created_at else "",
        chain_id=settings.CHAIN_ID,
        proof_fingerprint=proof.fingerprint_hash if proof else None,
        on_chain_state=chain_state,
        attempt_count=len(attempts),
        assigned_node_id=str(assigned_node.id) if assigned_node else None,
        assigned_gpu_name=assigned_node.gpu_name if assigned_node else None,
        assigned_provider_address=assigned_provider.wallet_address if assigned_provider else None,
        current_lease_status=lease.status if lease else None,
        proof_verification_status=("valid" if proof.valid else "invalid")
        if proof and proof.valid is not None
        else ("pending" if proof else None),
        result_available=bool(job.result_file_key and job.result_output_hash),
        result_download_endpoint=f"/v1/jobs/{job.id}/result"
        if job.result_file_key and job.result_output_hash
        else None,
        escrow_transaction=tx("createJob"),
        assignment_transaction=tx("assignProvider"),
        proof_transaction=tx("submitProof"),
        settlement_transaction=tx("verifyJob"),
        refund_transaction=refund_transaction,
        refund_status=refund_payment.status if refund_payment else None,
        provider_payment_credit_status=next((p.status for p in payments if p.payment_type == "provider_credit"), None),
        reconciliation_health="critical_incident"
        if incident or (cursor and cursor.halted)
        else "match"
        if chain_state in {"Settled", "Refunded"} and job.status in {"completed", "refunded"}
        else "pending",
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )
    return response


@router.get("/{job_id}/result")
async def download_job_result(
    job_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    try:
        job = await get_job(db, uuid.UUID(job_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job ID format") from exc
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your job")
    if not job.result_file_key or not job.result_output_hash:
        raise HTTPException(status_code=404, detail="Result not available")
    result_key = job.result_file_key
    result_hash = job.result_output_hash
    await db.commit()
    try:
        data = await storage.get_object(result_key)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Result not available") from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Result storage unavailable") from exc
    if hashlib.sha256(data).hexdigest() != result_hash:
        raise HTTPException(status_code=503, detail="Stored result failed integrity check")
    return Response(data, media_type="application/octet-stream")
