import hashlib
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Node


def generate_api_key() -> tuple[str, str]:
    """Generate API key and return (plaintext, sha256_hash)."""
    key = f"nb_live_{secrets.token_hex(32)}"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return key, key_hash


async def register_node(
    db: AsyncSession,
    provider_id: uuid.UUID,
    gpu_name: str | None,
    vram_gb: int | None,
    location: str | None,
    worker_signer_address: str | None,
) -> tuple[Node, str]:
    """Register a new GPU node. Returns (node, plaintext_api_key)."""
    api_key, api_key_hash = generate_api_key()

    node = Node(
        provider_id=provider_id,
        gpu_name=gpu_name,
        vram_gb=vram_gb,
        location=location,
        status="pending",
        worker_signer_address=worker_signer_address,
        api_key_hash=api_key_hash,
    )
    db.add(node)
    await db.flush()
    return node, api_key


async def get_node_by_api_key_hash(db: AsyncSession, api_key_hash: str) -> Node | None:
    result = await db.execute(select(Node).where(Node.api_key_hash == api_key_hash))
    return result.scalar_one_or_none()


async def rotate_node_credentials(db: AsyncSession, node: Node) -> tuple[Node, str]:
    """Rotate node API key. Returns (node, new_plaintext_api_key)."""
    api_key, api_key_hash = generate_api_key()
    node.api_key_hash = api_key_hash
    await db.flush()
    return node, api_key


async def update_heartbeat(db: AsyncSession, node: Node) -> None:
    """Update node heartbeat timestamp (database-only, no contract call)."""
    from datetime import datetime, timezone

    node.last_heartbeat = datetime.now(timezone.utc)
    await db.flush()
