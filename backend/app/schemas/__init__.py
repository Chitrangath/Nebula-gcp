from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProblemResponse(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | list[dict[str, Any]]
    instance: str


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
    worker_signer_address: str | None


class RotateNodeCredentialResponse(BaseModel):
    node_id: str
    api_key: str


class RotateWorkerSignerRequest(BaseModel):
    worker_signer_address: str = Field(..., pattern=r"^0x[0-9a-fA-F]{40}$")


class RotateWorkerSignerResponse(BaseModel):
    node_id: str
    worker_signer_address: str


class EarningCreditResponse(BaseModel):
    job_id: str
    amount_base_units: str
    status: str
    blockchain_tx_hash: str | None
    withdrawal_tx_hash: str | None
    credited_at: datetime | None
    withdrawn_at: datetime | None


class EarningsResponse(BaseModel):
    provider_id: str
    total_credited_base_units: str
    total_withdrawn_base_units: str
    pending_withdrawal_base_units: str | None
    pending_withdrawal_status: str
    credits: list[EarningCreditResponse]


class HeartbeatRequest(BaseModel):
    node_id: str


class HealthResponse(BaseModel):
    status: str
    version: str
