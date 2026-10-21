"""Runtime adapter lookup for HTTP handlers and independently run coordinators."""

from fastapi import HTTPException, Request

from app.services.blockchain_service import BlockchainBackend
from app.services.storage import StorageBackend


def get_blockchain(request: Request) -> BlockchainBackend:
    backend = getattr(request.app.state, "blockchain", None)
    if backend is None:
        raise HTTPException(status_code=503, detail="Blockchain runtime is not configured")
    return backend


def get_storage(request: Request) -> StorageBackend:
    storage = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(status_code=503, detail="Storage runtime is not configured")
    return storage
