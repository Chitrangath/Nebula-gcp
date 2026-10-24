"""Authenticated, credential-free projection of the live demo network."""

from datetime import datetime, timedelta, timezone
from typing import Literal, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Job, Lease, Node, User
from app.security import get_current_user

router = APIRouter()


class NetworkViewerResponse(BaseModel):
    user_id: str
    wallet_address: str
    role: Literal["ai_user", "gpu_provider"]


class NetworkLeaseResponse(BaseModel):
    chain_job_id: str
    model_id: str
    status: str
    expires_at: datetime


class NetworkCompletedJobResponse(BaseModel):
    chain_job_id: str
    model_id: str
    completed_at: datetime | None


class NetworkNodeResponse(BaseModel):
    id: str
    gpu_name: str | None
    vram_gb: int | None
    provider_wallet_address: str
    roles: list[Literal["gpu_provider", "verifier"]]
    status: str
    last_heartbeat: datetime | None
    heartbeat_age_seconds: int | None
    supported_models: list[str]
    active_lease: NetworkLeaseResponse | None
    last_completed_job: NetworkCompletedJobResponse | None


class NetworkSnapshotResponse(BaseModel):
    observed_at: datetime
    chain_id: int
    heartbeat_ttl_seconds: int
    verifier_address: str | None
    viewer: NetworkViewerResponse
    nodes: list[NetworkNodeResponse]


def _as_utc(heartbeat: datetime | None) -> datetime | None:
    if heartbeat is None:
        return None
    if heartbeat.tzinfo is None:
        return heartbeat.replace(tzinfo=timezone.utc)
    return heartbeat


def _heartbeat_age(observed_at: datetime, heartbeat: datetime | None) -> int | None:
    heartbeat = _as_utc(heartbeat)
    return None if heartbeat is None else max(0, int((observed_at - heartbeat).total_seconds()))


def _effective_status(node: Node, observed_at: datetime) -> str:
    status = cast(str | None, node.status) or "pending"
    heartbeat = _as_utc(cast(datetime | None, node.last_heartbeat))
    cutoff = observed_at - timedelta(seconds=settings.NODE_HEARTBEAT_TTL_SECONDS)
    if status == "online" and (heartbeat is None or heartbeat < cutoff):
        return "offline"
    return status


def _supported_models(node: Node) -> list[str]:
    models = ["resnet50"] if node.cuda_capable else []
    if node.cuda_capable and node.supports_bert:
        models.append("bert-base")
    return models


@router.get("", response_model=NetworkSnapshotResponse)
async def get_network_snapshot(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NetworkSnapshotResponse:
    """Return public identities and backend-observed state for demo participants."""
    observed_at = datetime.now(timezone.utc)
    node_rows = list(
        (
            await db.execute(
                select(Node, User)
                .join(User, User.id == Node.provider_id)
                .order_by(Node.created_at, Node.id)
            )
        ).all()
    )
    node_ids = [node.id for node, _provider in node_rows]
    active_by_node: dict[object, tuple[Lease, Job]] = {}
    completed_by_node: dict[object, Job] = {}
    if node_ids:
        active_rows = (
            await db.execute(
                select(Lease, Job)
                .join(Job, Job.id == Lease.job_id)
                .where(
                    Lease.node_id.in_(node_ids),
                    Lease.status.in_(("pending_chain", "active")),
                    Job.current_lease_id == Lease.id,
                )
                .order_by(Lease.created_at.desc(), Lease.id.desc())
            )
        ).all()
        for lease, job in active_rows:
            active_by_node.setdefault(lease.node_id, (lease, job))

        completed_rank = func.row_number().over(
            partition_by=Job.assigned_node_id,
            order_by=(Job.completed_at.desc().nulls_last(), Job.id.desc()),
        ).label("completed_rank")
        ranked_completed = (
            select(Job.id.label("job_id"), completed_rank)
            .where(Job.assigned_node_id.in_(node_ids), Job.status == "completed")
            .subquery()
        )
        completed_jobs = list(
            (
                await db.execute(
                    select(Job)
                    .join(ranked_completed, ranked_completed.c.job_id == Job.id)
                    .where(ranked_completed.c.completed_rank == 1)
                )
            )
            .scalars()
            .all()
        )
        for job in completed_jobs:
            completed_by_node.setdefault(job.assigned_node_id, job)

    verifier_address = settings.CONTRACT_VERIFIER_ADDRESS or None
    verifier_node_id = settings.DEMO_VERIFIER_NODE_ID.lower()
    nodes: list[NetworkNodeResponse] = []
    for node, provider in node_rows:
        heartbeat_age = _heartbeat_age(observed_at, node.last_heartbeat)
        roles: list[Literal["gpu_provider", "verifier"]] = ["gpu_provider"]
        if verifier_node_id and str(node.id).lower() == verifier_node_id:
            roles.append("verifier")
        active = active_by_node.get(node.id)
        completed = completed_by_node.get(node.id)
        nodes.append(
            NetworkNodeResponse(
                id=str(node.id),
                gpu_name=node.gpu_name,
                vram_gb=node.vram_gb,
                provider_wallet_address=provider.wallet_address,
                roles=roles,
                status=_effective_status(node, observed_at),
                last_heartbeat=node.last_heartbeat,
                heartbeat_age_seconds=heartbeat_age,
                supported_models=_supported_models(node),
                active_lease=NetworkLeaseResponse(
                    chain_job_id=cast(str, active[1].chain_job_id),
                    model_id=cast(str, active[1].model_id),
                    status=cast(str, active[0].status),
                    expires_at=cast(datetime, active[0].expires_at),
                )
                if active
                else None,
                last_completed_job=NetworkCompletedJobResponse(
                    chain_job_id=cast(str, completed.chain_job_id),
                    model_id=cast(str, completed.model_id),
                    completed_at=cast(datetime | None, completed.completed_at),
                )
                if completed
                else None,
            )
        )

    return NetworkSnapshotResponse(
        observed_at=observed_at,
        chain_id=settings.CHAIN_ID,
        heartbeat_ttl_seconds=settings.NODE_HEARTBEAT_TTL_SECONDS,
        verifier_address=verifier_address,
        viewer=NetworkViewerResponse(
            user_id=str(user.id),
            wallet_address=cast(str, user.wallet_address),
            role="gpu_provider" if user.role == "provider" else "ai_user",
        ),
        nodes=nodes,
    )
