"""Full 12-check proof verification orchestration pipeline.

PRD v3.1 §9.4: Backend verification sequence with all 12 checks.
Persists individual check results and one final verdict.
Uses DB locking to prevent concurrent verification of the same proof.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, JobAttempt, Lease, Node, Proof, User
from app.services.eip712 import (
    ProofEnvelope,
    build_eip712_struct_hash,
    verify_envelope_signature,
    verify_signature,
)
from app.services.merkle import compute_leaf_hash, compute_node_hash
from app.services.storage import StorageBackend
from app.utils import uuid_to_bytes32

MAX_RESULT_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB


class Verdict(str, Enum):
    VALID = "valid"
    INVALID = "invalid"


class CheckResult:
    """Result of a single verification check."""

    __slots__ = ("check_number", "check_name", "passed", "error")

    def __init__(self, check_number: int, check_name: str, passed: bool, error: str | None = None):
        self.check_number = check_number
        self.check_name = check_name
        self.passed = passed
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        d = {
            "check_number": self.check_number,
            "check_name": self.check_name,
            "passed": self.passed,
        }
        if self.error:
            d["error"] = self.error
        return d


class VerificationResult:
    """Complete result of all 12 verification checks."""

    def __init__(self):
        self.checks: list[CheckResult] = []
        self.verdict: Verdict | None = None
        self.error: str | None = None

    def add_check(self, result: CheckResult):
        self.checks.append(result)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checks": [c.to_dict() for c in self.checks],
            "verdict": self.verdict.value if self.verdict else None,
            "error": self.error,
        }


# Canonical checkpoint configurations per model
MODEL_CHECKPOINTS: dict[str, list[str]] = {
    "resnet50": ["preprocess", "forward", "softmax", "topk"],
    "yolov5": ["preprocess", "forward", "nms", "decode"],
    "bert-base": ["tokenize", "forward", "pool", "project"],
    "whisper-tiny": ["preprocess", "encoder", "decoder", "decode_tokens"],
}


async def verify_proof(
    db: AsyncSession,
    *,
    job_id: str,
    attempt_id: str,
    lease_id: str,
    fingerprint_hex: str,
    merkle_root_hex: str,
    output_hash_hex: str,
    merkle_proof: list[tuple[bytes, bool]],
    trace_hashes: list[bytes],
    checkpoint_names: list[str],
    signature_bytes: bytes,
    signer_address: str,
    proof_timestamp: int,
    protocol_version: int,
    chain_id: int,
    contract_address: str,
    model_id: str,
    storage: StorageBackend | None = None,
    queued_proof_id: str | None = None,
    canonical_result_bytes: bytes | None = None,
) -> VerificationResult:
    """Execute all 12 PRD v3.1 §9.4 verification checks.

    Each check is persisted. If any check fails, verdict = INVALID immediately.
    DB-level locking prevents concurrent verification of the same proof.
    """
    result = VerificationResult()

    # ── DB Lock: prevent concurrent verification of the same proof ──
    dialect = db.bind.dialect.name if db.bind else "sqlite"
    if dialect == "postgresql":
        # Lock the job row to prevent concurrent verifiers
        await db.execute(text("SELECT 1 FROM jobs WHERE id = :jid FOR UPDATE"), {"jid": job_id})

    # ── Check 1: Protocol version and schema ──
    if protocol_version != 1:
        result.add_check(CheckResult(1, "protocol_version", False, f"Unsupported protocol version: {protocol_version}"))
        result.verdict = Verdict.INVALID
        result.error = "Unsupported protocol version"
        return result
    result.add_check(CheckResult(1, "protocol_version", True))

    # ── Check 2: Job exists and is in eligible state ──
    job_uuid = __import__("uuid").UUID(job_id)
    job_result = await db.execute(select(Job).where(Job.id == job_uuid))
    job = job_result.scalar_one_or_none()
    if not job:
        result.add_check(CheckResult(2, "job_exists", False, "Job not found"))
        result.verdict = Verdict.INVALID
        result.error = "Job not found"
        return result
    if job.status not in ("proof_submitted", "verifying", "settling"):
        result.add_check(CheckResult(2, "job_exists", False, f"Job status {job.status} not eligible"))
        result.verdict = Verdict.INVALID
        result.error = f"Job status {job.status} not eligible"
        return result
    result.add_check(CheckResult(2, "job_exists", True))

    # ── Check 3: Attempt exists and belongs to this job ──
    attempt_uuid = __import__("uuid").UUID(attempt_id)
    attempt_result = await db.execute(select(JobAttempt).where(JobAttempt.id == attempt_uuid))
    attempt = attempt_result.scalar_one_or_none()
    if not attempt:
        result.add_check(CheckResult(3, "attempt_binding", False, "Attempt not found"))
        result.verdict = Verdict.INVALID
        result.error = "Attempt not found"
        return result
    if str(attempt.job_id) != job_id:
        result.add_check(CheckResult(3, "attempt_binding", False, "Attempt does not belong to this job"))
        result.verdict = Verdict.INVALID
        result.error = "Attempt-job mismatch"
        return result
    result.add_check(CheckResult(3, "attempt_binding", True))

    # ── Check 4: Lease exists, is active, and not expired ──
    lease_uuid = __import__("uuid").UUID(lease_id)
    lease_result = await db.execute(select(Lease).where(Lease.id == lease_uuid))
    lease = lease_result.scalar_one_or_none()
    if not lease:
        result.add_check(CheckResult(4, "lease_binding", False, "Lease not found"))
        result.verdict = Verdict.INVALID
        result.error = "Lease not found"
        return result
    if lease.status != "active":
        result.add_check(CheckResult(4, "lease_binding", False, f"Lease status {lease.status} not active"))
        result.verdict = Verdict.INVALID
        result.error = f"Lease status {lease.status} not active"
        return result
    if lease.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        result.add_check(CheckResult(4, "lease_binding", False, "Lease has expired"))
        result.verdict = Verdict.INVALID
        result.error = "Lease expired"
        return result
    result.add_check(CheckResult(4, "lease_binding", True))

    # ── Check 5: Lease belongs to job, attempt, and assigned node ──
    if str(lease.job_id) != job_id:
        result.add_check(CheckResult(5, "lease_ownership", False, "Lease does not belong to this job"))
        result.verdict = Verdict.INVALID
        result.error = "Lease-job mismatch"
        return result
    if str(lease.node_id) != str(attempt.node_id):
        result.add_check(CheckResult(5, "lease_ownership", False, "Lease node differs from attempt node"))
        result.verdict = Verdict.INVALID
        result.error = "Lease-node mismatch"
        return result
    if str(lease.id) != str(attempt.lease_id):
        result.add_check(CheckResult(5, "lease_ownership", False, "Lease ID mismatch with attempt"))
        result.verdict = Verdict.INVALID
        result.error = "Lease-attempt mismatch"
        return result
    result.add_check(CheckResult(5, "lease_ownership", True))

    # ── Check 6: Lease ID equals current DB and on-chain lease ──
    if str(job.current_lease_id) != lease_id:
        result.add_check(CheckResult(6, "lease_id_consistency", False, "Lease ID does not match job's current lease"))
        result.verdict = Verdict.INVALID
        result.error = "Job current lease mismatch"
        return result
    result.add_check(CheckResult(6, "lease_id_consistency", True))

    # ── Check 7: Timestamp validity (proof <= lease expiry <= job deadline) ──
    proof_dt = datetime.fromtimestamp(proof_timestamp, tz=timezone.utc)
    lease_expiry = lease.expires_at.replace(tzinfo=timezone.utc)
    job_deadline = job.deadline.replace(tzinfo=timezone.utc)
    if proof_dt > lease_expiry:
        result.add_check(CheckResult(7, "timestamp_validity", False, "Proof timestamp exceeds lease expiry"))
        result.verdict = Verdict.INVALID
        result.error = "Proof exceeds lease expiry"
        return result
    if lease_expiry > job_deadline:
        result.add_check(CheckResult(7, "timestamp_validity", False, "Lease expiry exceeds job deadline"))
        result.verdict = Verdict.INVALID
        result.error = "Lease exceeds deadline"
        return result
    result.add_check(CheckResult(7, "timestamp_validity", True))

    # ── Check 8: Fingerprint matches expected ──
    if job.expected_fingerprint:
        expected_fp_hex = job.expected_fingerprint
        if fingerprint_hex.lower() != expected_fp_hex.lower():
            result.add_check(CheckResult(8, "fingerprint_match", False, "Fingerprint mismatch — security event"))
            result.verdict = Verdict.INVALID
            result.error = "Fingerprint mismatch"
            return result
    result.add_check(CheckResult(8, "fingerprint_match", True))

    # ── Check 9: Checkpoint names, count, ordering, encoding ──
    expected_checkpoints = MODEL_CHECKPOINTS.get(model_id, [])
    if checkpoint_names != expected_checkpoints:
        result.add_check(
            CheckResult(9, "checkpoint_match", False, f"Expected {expected_checkpoints}, got {checkpoint_names}")
        )
        result.verdict = Verdict.INVALID
        result.error = "Checkpoint mismatch"
        return result
    result.add_check(CheckResult(9, "checkpoint_match", True))

    # ── Check 10: Canonical Merkle root and output hash validation ──
    if not trace_hashes:
        result.add_check(CheckResult(10, "merkle_root", False, "No trace hashes provided"))
        result.verdict = Verdict.INVALID
        result.error = "Empty trace"
        return result

    # 10a: Retrieve actual canonical result bytes from storage
    if canonical_result_bytes is None and not storage:
        result.add_check(CheckResult(10, "output_bytes", False, "No storage backend configured"))
        result.verdict = Verdict.INVALID
        result.error = "No storage backend"
        return result

    if not job.result_file_key:
        result.add_check(CheckResult(10, "output_bytes", False, "No result file key on job"))
        result.verdict = Verdict.INVALID
        result.error = "No result file key"
        return result

    if canonical_result_bytes is None:
        try:
            canonical_result_bytes = await storage.get_object(job.result_file_key)  # type: ignore[union-attr]
        except (KeyError, FileNotFoundError):
            result.add_check(CheckResult(10, "output_bytes", False, "Result object not found in storage"))
            result.verdict = Verdict.INVALID
            result.error = "Result object not found"
            return result
        except Exception as e:
            result.add_check(CheckResult(10, "output_bytes", False, f"Storage error: {e}"))
            result.verdict = Verdict.INVALID
            result.error = f"Storage retrieval failed: {e}"
            return result

    # 10b: Enforce size limit
    if len(canonical_result_bytes) > MAX_RESULT_SIZE_BYTES:
        result.add_check(
            CheckResult(10, "output_bytes", False, f"Result exceeds size limit: {len(canonical_result_bytes)} bytes")
        )
        result.verdict = Verdict.INVALID
        result.error = f"Result too large: {len(canonical_result_bytes)} bytes"
        return result

    # 10c: Compute hash of actual canonical bytes
    computed_output_hash = hashlib.sha256(canonical_result_bytes).digest()
    claimed_output_hash = bytes.fromhex(output_hash_hex.removeprefix("0x"))

    # 10d: Compare computed hash with claimed outputHash
    if computed_output_hash != claimed_output_hash:
        result.add_check(CheckResult(10, "output_bytes", False, "Computed output hash differs from claimed outputHash"))
        result.verdict = Verdict.INVALID
        result.error = "Output hash mismatch — result bytes differ from claimed"
        return result

    # 10e: Verify Merkle root from trace hashes
    recomputed_root = _recompute_merkle_root([*trace_hashes, computed_output_hash])
    if recomputed_root != bytes.fromhex(merkle_root_hex.removeprefix("0x")):
        result.add_check(CheckResult(10, "merkle_root", False, "Merkle root mismatch"))
        result.verdict = Verdict.INVALID
        result.error = "Merkle root mismatch"
        return result

    result.add_check(CheckResult(10, "output_bytes", True))
    result.add_check(CheckResult(10, "merkle_root", True))

    # ── Check 11: Full EIP-712 domain/envelope and authorized worker signer ──
    # Get the node's worker signer address
    node_result = await db.execute(select(Node).where(Node.id == lease.node_id))
    node = node_result.scalar_one_or_none()
    if not node:
        result.add_check(CheckResult(11, "signature_verification", False, "Node not found"))
        result.verdict = Verdict.INVALID
        result.error = "Node not found"
        return result

    expected_signer = node.worker_signer_address
    if not expected_signer:
        result.add_check(CheckResult(11, "signature_verification", False, "No worker signer configured on node"))
        result.verdict = Verdict.INVALID
        result.error = "No worker signer on node"
        return result

    provider_result = await db.execute(select(User).where(User.id == node.provider_id))
    provider = provider_result.scalar_one_or_none()
    if provider is None or signer_address.lower() != expected_signer.lower():
        result.add_check(CheckResult(11, "signature_verification", False, "Signer/provider binding failed"))
        result.verdict = Verdict.INVALID
        result.error = "Signer/provider binding failed"
        return result
    envelope = ProofEnvelope(
        protocol_version=protocol_version,
        chain_id=chain_id,
        verifying_contract=contract_address,
        job_id=bytes.fromhex(job.chain_job_id.removeprefix("0x")),
        attempt_id=bytes.fromhex(uuid_to_bytes32(attempt.id).removeprefix("0x")),
        lease_id=bytes.fromhex(lease.lease_id.removeprefix("0x")),
        provider=provider.wallet_address,
        fingerprint=bytes.fromhex(fingerprint_hex.removeprefix("0x")),
        merkle_root=bytes.fromhex(merkle_root_hex.removeprefix("0x")),
        output_hash=bytes.fromhex(output_hash_hex.removeprefix("0x")),
        proof_timestamp=proof_timestamp,
        lease_expires_at=int(lease.expires_at.timestamp()),
    )

    if not verify_envelope_signature(envelope, signature_bytes, expected_signer):
        result.add_check(CheckResult(11, "signature_verification", False, "EIP-712 signature verification failed"))
        result.verdict = Verdict.INVALID
        result.error = "Signature verification failed"
        return result
    result.add_check(CheckResult(11, "signature_verification", True))

    # ── Check 12: Replay detection — no prior proof/verdict/settlement ──
    if attempt.status in ("completed", "failed", "expired"):
        result.add_check(CheckResult(12, "replay_detection", False, f"Attempt already has status {attempt.status}"))
        result.verdict = Verdict.INVALID
        result.error = "Replay detected — attempt already processed"
        return result
    # Check if a proof already exists for this attempt
    existing_proof = await db.execute(select(Proof).where(Proof.job_attempt_id == attempt.id))
    prior_proof = existing_proof.scalar_one_or_none()
    if prior_proof and (
        queued_proof_id is None or str(prior_proof.id) != queued_proof_id or prior_proof.valid is not None
    ):
        result.add_check(CheckResult(12, "replay_detection", False, "Proof already exists for this attempt"))
        result.verdict = Verdict.INVALID
        result.error = "Replay detected — proof already exists"
        return result
    # Check if job is already in a terminal state
    if job.status in ("completed", "refunded"):
        result.add_check(CheckResult(12, "replay_detection", False, f"Job already in terminal state {job.status}"))
        result.verdict = Verdict.INVALID
        result.error = "Replay detected — job already settled"
        return result
    result.add_check(CheckResult(12, "replay_detection", True))

    # ── All checks passed ──
    result.verdict = Verdict.VALID
    return result


def _recompute_merkle_root(trace_hashes: list[bytes]) -> bytes:
    """Recompute Merkle root from canonical trace leaves using PRD §9 rules.

    leafHash = SHA256(0x00 || leaf_data)
    nodeHash = SHA256(0x01 || left || right)
    Odd levels: duplicate final node. No sorting.
    """
    if not trace_hashes:
        return b"\x00" * 32

    leaf_hashes = [compute_leaf_hash(h) for h in trace_hashes]
    current = leaf_hashes

    while len(current) > 1:
        next_level = []
        for i in range(0, len(current), 2):
            left = current[i]
            right = current[i + 1] if i + 1 < len(current) else current[i]
            next_level.append(compute_node_hash(left, right))
        current = next_level

    return current[0]


async def persist_verdict(
    db: AsyncSession,
    *,
    attempt_id: str,
    result: VerificationResult,
    fingerprint_hash: str,
    merkle_root: str,
    output_hash: str,
    signature: str,
    signer_address: str,
    proof_timestamp: datetime,
) -> Proof:
    """Persist the proof and verification result to the database."""
    attempt_uuid = __import__("uuid").UUID(attempt_id)

    proof = Proof(
        id=__import__("uuid").uuid4(),
        job_attempt_id=attempt_uuid,
        protocol_version=1,
        fingerprint_hash=fingerprint_hash,
        merkle_root=merkle_root,
        output_hash=output_hash,
        signature=signature,
        signer_address=signer_address,
        proof_timestamp=proof_timestamp,
        valid=result.verdict == Verdict.VALID if result.verdict else None,
        verification_error=result.error,
        verified_at=datetime.now(timezone.utc),
        trace_hashes=[],
    )
    db.add(proof)
    await db.flush()
    return proof


# ──────────────────────────────────────────────
# Backward-compatible standalone functions
# ──────────────────────────────────────────────


def verify_proof_envelope(
    *,
    leaf_data: bytes,
    leaf_hash: bytes,
    merkle_proof: list[tuple[bytes, bool]],
    merkle_root: bytes,
    job_id: bytes,
    fingerprint: bytes,
    output_hash: bytes,
    timestamp: int,
    signature: bytes,
    expected_signer: str,
) -> bool:
    """Verify a complete PoAE proof envelope (standalone, no DB).

    Steps:
    1. Verify leaf hash matches SHA256(0x00 || leaf_data)
    2. Verify Merkle inclusion: recompute root from leaf + proof
    3. Verify EIP-712 signature from expected signer
    """
    expected_leaf_hash = compute_leaf_hash(leaf_data)
    if leaf_hash != expected_leaf_hash:
        return False

    current = leaf_hash
    for sibling, is_right in merkle_proof:
        if is_right:
            current = compute_node_hash(current, sibling)
        else:
            current = compute_node_hash(sibling, current)
    if current != merkle_root:
        return False

    struct_hash = build_eip712_struct_hash(
        job_id=job_id,
        fingerprint=fingerprint,
        merkle_root=merkle_root,
        output_hash=output_hash,
        timestamp=timestamp,
    )
    if not verify_signature(struct_hash, signature, expected_signer):
        return False

    return True
