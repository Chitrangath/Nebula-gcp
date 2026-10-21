from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Node, User
from app.schemas import HeartbeatRequest, NodeResponse, RegisterNodeRequest, RegisterNodeResponse
from app.security import get_current_user
from app.services.node_service import register_node, update_heartbeat

router = APIRouter()


@router.post("", response_model=RegisterNodeResponse)
async def create_node(
    req: RegisterNodeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
async def list_nodes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Node).where(Node.status.in_(["online", "pending"])))
    nodes = result.scalars().all()
    return [
        NodeResponse(
            id=str(n.id),
            gpu_name=n.gpu_name,
            vram_gb=n.vram_gb,
            status=n.status or "pending",
            last_heartbeat=n.last_heartbeat,
            active_leases=n.active_leases or 0,
        )
        for n in nodes
    ]


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(node_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return NodeResponse(
        id=str(node.id),
        gpu_name=node.gpu_name,
        vram_gb=node.vram_gb,
        status=node.status or "pending",
        last_heartbeat=node.last_heartbeat,
        active_leases=node.active_leases or 0,
    )


@router.post("/heartbeat")
async def node_heartbeat(
    req: HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Node).where(Node.id == req.node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    await update_heartbeat(db, node)
    return {"detail": "Heartbeat recorded"}
