from datetime import datetime

from pydantic import BaseModel, Field


class ChallengeRequest(BaseModel):
    wallet_address: str = Field(..., pattern=r"^0x[0-9a-f]{40}$")


class ChallengeResponse(BaseModel):
    challenge: str
    nonce: str
    expires_at: datetime


class VerifyRequest(BaseModel):
    wallet_address: str = Field(..., pattern=r"^0x[0-9a-f]{40}$")
    signature: str
    nonce: str


class VerifyResponse(BaseModel):
    access_token: str
    expires_in: int = 86400


class RefreshResponse(BaseModel):
    access_token: str
    expires_in: int = 86400


class RegisterNodeRequest(BaseModel):
    gpu_name: str | None = None
    vram_gb: int | None = None
    location: str | None = None
    worker_signer_address: str | None = None


class RegisterNodeResponse(BaseModel):
    node_id: str
    api_key: str
    status: str


class NodeResponse(BaseModel):
    id: str
    gpu_name: str | None
    vram_gb: int | None
    status: str
    last_heartbeat: datetime | None
    active_leases: int


class HeartbeatRequest(BaseModel):
    node_id: str


class HealthResponse(BaseModel):
    status: str
    version: str
