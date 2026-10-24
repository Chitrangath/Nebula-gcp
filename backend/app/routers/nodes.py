import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Job, Lease, Node, User
from app.schemas import (
    NodeJobResponse,
    NodeLeaseResponse,
    NodeResponse,
    RegisterNodeRequest,
    RegisterNodeResponse,
    RotateNodeCredentialResponse,
    RotateWorkerSignerRequest,
    RotateWorkerSignerResponse,
)
from app.security import get_current_user
from app.services.node_service import generate_api_key, register_node, rotate_node_credentials

router = APIRouter()


def _require_provider(user: User) -> None:
    if user.role != "provider":
        raise HTTPException(status_code=403, detail="Provider role required")


async def _owned_node(db: AsyncSession, user: User, node_id: uuid.UUID) -> Node:
    result = await db.execute(select(Node).where(Node.id == node_id, Node.provider_id == user.id))
    node = result.scalar_one_or_none()
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


async def _node_response(db: AsyncSession, node: Node) -> NodeResponse:
    active_row = (
        await db.execute(
            select(Lease, Job)
            .join(Job, Job.id == Lease.job_id)
            .where(Lease.node_id == node.id, Lease.status.in_(("pending_chain", "active")))
            .order_by(Lease.created_at.desc(), Lease.id.desc())
            .limit(1)
        )
    ).first()
    recent_jobs = list(
        (
            await db.execute(
                select(Job)
                .where(Job.assigned_node_id == node.id, Job.status == "completed")
                .order_by(Job.completed_at.desc(), Job.id.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    supported_models = ["resnet50"] if node.cuda_capable else []
    if node.cuda_capable and node.supports_bert:
        supported_models.append("bert-base")
    active_lease = None
    if active_row is not None:
        lease, job = active_row
        active_lease = NodeLeaseResponse(
            job_id=str(job.id),
            model_id=job.model_id,
            status=lease.status,
            expires_at=lease.expires_at,
        )
    return NodeResponse(
        id=str(node.id),
        gpu_name=node.gpu_name,
        vram_gb=node.vram_gb,
        status=node.status or "pending",
        last_heartbeat=node.last_heartbeat,
        active_leases=node.active_leases or 0,
        worker_signer_address=node.worker_signer_address,
        supported_models=supported_models,
        active_lease=active_lease,
        recent_jobs=[
            NodeJobResponse(
                job_id=str(job.id),
                model_id=job.model_id,
                status=job.status,
                completed_at=job.completed_at,
            )
            for job in recent_jobs
        ],
    )


@router.post("", response_model=RegisterNodeResponse)
async def create_node(
    req: RegisterNodeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RegisterNodeResponse:
    _require_provider(user)
    node, api_key = await register_node(
        db,
        provider_id=user.id,
        gpu_name=req.gpu_name,
        vram_gb=req.vram_gb,
        location=req.location,
        worker_signer_address=req.worker_signer_address,
    )
    return RegisterNodeResponse(
        node_id=str(node.id),
        api_key=api_key,
        status=node.status or "pending",
    )


@router.get("", response_model=list[NodeResponse])
async def list_nodes(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NodeResponse]:
    _require_provider(user)
    result = await db.execute(select(Node).where(Node.provider_id == user.id).order_by(Node.created_at, Node.id))
    nodes = result.scalars().all()
    return [await _node_response(db, node) for node in nodes]


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(
    node_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NodeResponse:
    _require_provider(user)
    node = await _owned_node(db, user, node_id)
    return await _node_response(db, node)


@router.post("/{node_id}/credentials/rotate", response_model=RotateNodeCredentialResponse)
async def rotate_credentials(
    node_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RotateNodeCredentialResponse:
    """Rotate a provider-owned credential and display the replacement once."""
    _require_provider(user)
    node = await _owned_node(db, user, node_id)
    node, api_key = await rotate_node_credentials(db, node)
    return RotateNodeCredentialResponse(node_id=str(node.id), api_key=api_key)


@router.post("/{node_id}/credentials/revoke", status_code=204)
async def revoke_credentials(
    node_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Invalidate a provider-owned credential without returning a replacement."""
    _require_provider(user)
    node = await _owned_node(db, user, node_id)
    _, replacement_hash = generate_api_key()
    node.api_key_hash = replacement_hash
    node.status = "disabled"
    await db.flush()


@router.post("/{node_id}/worker-signer/rotate", response_model=RotateWorkerSignerResponse)
async def rotate_worker_signer(
    node_id: uuid.UUID,
    req: RotateWorkerSignerRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RotateWorkerSignerResponse:
    """Replace the only signer accepted for future proofs from a node."""
    _require_provider(user)
    node = await _owned_node(db, user, node_id)
    node.worker_signer_address = req.worker_signer_address
    await db.flush()
    return RotateWorkerSignerResponse(
        node_id=str(node.id),
        worker_signer_address=node.worker_signer_address,
    )
