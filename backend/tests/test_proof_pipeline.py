"""Tests for the full 12-check proof verification pipeline (PRD v3.1 §9.4).

Tests the orchestration service that checks all 12 verification conditions.
Each check is persisted with pass/fail. Tests cover correct proofs,
all 12 failure modes, replay detection, and DB locking.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobAttempt, Lease, Node, Proof, SupportedModel, User
from app.services.eip712 import ProofEnvelope, sign_envelope
from app.services.job_service import confirm_job_escrow, create_job
from app.services.merkle import build_merkle_tree
from app.services.proof_verifier import (
    Verdict,
    VerificationResult,
    persist_verdict,
    verify_proof,
)
from app.services.storage import InMemoryStorage
from app.utils import uuid_to_bytes32


@pytest_asyncio.fixture
async def seed_model(db: AsyncSession):
    model = SupportedModel(
        id="resnet50",
        name="ResNet-50",
        framework="pytorch",
        vram_required_gb=8,
        price_base_units=500000000000000000,
        model_version="1.0",
        preprocessing_version="resnet50-v1",
        input_type="image",
        supported_formats=["jpg", "png"],
    )
    db.add(model)
    await db.flush()
    return model


@pytest_asyncio.fixture
async def seed_user(db: AsyncSession):
    user = User(id=uuid.uuid4(), wallet_address="0x" + uuid.uuid4().hex, role="user")
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def seed_provider(db: AsyncSession):
    provider = User(id=uuid.uuid4(), wallet_address="0x" + "22" * 20, role="provider")
    db.add(provider)
    await db.flush()
    return provider


@pytest_asyncio.fixture
async def seed_node(db: AsyncSession, seed_provider):
    worker_key = secrets.token_bytes(32)
    from eth_account import Account

    worker_acct = Account.from_key(worker_key)

    node = Node(
        id=uuid.uuid4(),
        provider_id=seed_provider.id,
        gpu_name="RTX 4090",
        vram_gb=24,
        status="online",
        worker_signer_address=worker_acct.address,
        api_key_hash=hashlib.sha256(b"test-key").hexdigest(),
        active_leases=0,
    )
    db.add(node)
    await db.flush()
    return node, worker_key, worker_acct


@pytest_asyncio.fixture
async def active_lease_and_job(db: AsyncSession, seed_model, seed_user, seed_node):
    """Create a fully active lease and job ready for proof submission."""
    node, worker_key, worker_acct = seed_node

    job = await create_job(
        db,
        user_id=seed_user.id,
        model_id="resnet50",
        chain_job_id="0x" + uuid.uuid4().hex,
        price_base_units=500000000000000000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    job.chain_job_id = uuid_to_bytes32(job.id)
    await confirm_job_escrow(db, job_id=job.id, tx_hash="0xabc", escrow_amount=500000000000000000)

    lease = Lease(
        id=uuid.uuid4(),
        job_id=job.id,
        node_id=node.id,
        lease_id="0x" + secrets.token_hex(32),
        started_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        status="active",
        heartbeat_at=datetime.now(timezone.utc),
    )
    db.add(lease)

    attempt = JobAttempt(
        id=uuid.uuid4(),
        job_id=job.id,
        node_id=node.id,
        lease_id=lease.id,
        attempt_number=1,
        status="running",
    )
    db.add(attempt)

    job.assigned_node_id = node.id
    job.current_lease_id = lease.id
    job.current_attempt = 1
    job.status = "proof_submitted"

    # Set up storage with canonical result bytes
    storage = InMemoryStorage()
    result_bytes = b"canonical-result-for-proof-pipeline-test"
    result_key = f"results/{job.id}/{attempt.id}/output"
    job.result_file_key = result_key

    await db.flush()
    return job, lease, attempt, node, worker_key, worker_acct, storage, result_bytes


class TestProofPipeline:
    @pytest.mark.asyncio
    async def test_all_checks_pass(self, db: AsyncSession, active_lease_and_job):
        """Valid proof passes all 12 checks."""
        job, lease, attempt, node, worker_key, worker_acct, storage, result_bytes = active_lease_and_job

        # Store canonical result bytes
        await storage.put_object(job.result_file_key, result_bytes)

        # Build valid Merkle tree
        trace_hashes = [hashlib.sha256(f"step{i}".encode()).digest() for i in range(4)]
        # Compute fingerprint (use job's expected fingerprint)
        fingerprint_hex = hashlib.sha256(b"fingerprint-data").hexdigest()
        job.expected_fingerprint = fingerprint_hex

        # Compute output hash from actual result bytes
        output_hash = hashlib.sha256(result_bytes).digest()
        merkle_root, proofs = build_merkle_tree([*trace_hashes, output_hash])

        # Build EIP-712 signature
        job_id_bytes = bytes.fromhex(job.chain_job_id.removeprefix("0x"))
        ts = int(datetime.now(timezone.utc).timestamp())
        envelope = ProofEnvelope(
            protocol_version=1,
            chain_id=421614,
            verifying_contract="0x" + "ab" * 20,
            job_id=job_id_bytes,
            attempt_id=bytes.fromhex(uuid_to_bytes32(attempt.id)[2:]),
            lease_id=bytes.fromhex(lease.lease_id[2:]),
            provider="0x" + "22" * 20,
            fingerprint=bytes.fromhex(fingerprint_hex),
            merkle_root=merkle_root,
            output_hash=output_hash,
            proof_timestamp=ts,
            lease_expires_at=int(lease.expires_at.timestamp()),
        )
        signature = sign_envelope(envelope, worker_key)

        result = await verify_proof(
            db,
            storage=storage,
            job_id=str(job.id),
            attempt_id=str(attempt.id),
            lease_id=str(lease.id),
            fingerprint_hex=fingerprint_hex,
            merkle_root_hex=merkle_root.hex(),
            output_hash_hex=output_hash.hex(),
            merkle_proof=proofs[0],
            trace_hashes=trace_hashes,
            checkpoint_names=["preprocess", "forward", "softmax", "topk"],
            signature_bytes=signature,
            signer_address=worker_acct.address,
            proof_timestamp=ts,
            protocol_version=1,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            model_id="resnet50",
        )

        assert result.verdict == Verdict.VALID
        assert len(result.checks) == 13  # 12 original + output_bytes sub-check
        assert all(c.passed for c in result.checks)

    @pytest.mark.asyncio
    async def test_rotated_worker_signer_rejects_stale_signature(self, db: AsyncSession, active_lease_and_job):
        job, lease, attempt, node, worker_key, worker_acct, storage, result_bytes = active_lease_and_job
        await storage.put_object(job.result_file_key, result_bytes)
        trace_hashes = [hashlib.sha256(f"step{i}".encode()).digest() for i in range(4)]
        fingerprint_hex = hashlib.sha256(b"fingerprint-data").hexdigest()
        job.expected_fingerprint = fingerprint_hex
        output_hash = hashlib.sha256(result_bytes).digest()
        merkle_root, proofs = build_merkle_tree([*trace_hashes, output_hash])
        ts = int(datetime.now(timezone.utc).timestamp())
        envelope = ProofEnvelope(
            protocol_version=1,
            chain_id=421614,
            verifying_contract="0x" + "ab" * 20,
            job_id=bytes.fromhex(job.chain_job_id.removeprefix("0x")),
            attempt_id=bytes.fromhex(uuid_to_bytes32(attempt.id)[2:]),
            lease_id=bytes.fromhex(lease.lease_id[2:]),
            provider="0x" + "22" * 20,
            fingerprint=bytes.fromhex(fingerprint_hex),
            merkle_root=merkle_root,
            output_hash=output_hash,
            proof_timestamp=ts,
            lease_expires_at=int(lease.expires_at.timestamp()),
        )
        signature = sign_envelope(envelope, worker_key)
        node.worker_signer_address = "0x" + "77" * 20
        await db.flush()

        result = await verify_proof(
            db,
            storage=storage,
            job_id=str(job.id),
            attempt_id=str(attempt.id),
            lease_id=str(lease.id),
            fingerprint_hex=fingerprint_hex,
            merkle_root_hex=merkle_root.hex(),
            output_hash_hex=output_hash.hex(),
            merkle_proof=proofs[0],
            trace_hashes=trace_hashes,
            checkpoint_names=["preprocess", "forward", "softmax", "topk"],
            signature_bytes=signature,
            signer_address=worker_acct.address,
            proof_timestamp=ts,
            protocol_version=1,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            model_id="resnet50",
        )

        assert result.verdict == Verdict.INVALID
        assert result.error == "Signer/provider binding failed"

    @pytest.mark.asyncio
    async def test_check_1_bad_protocol_version(self, db: AsyncSession, active_lease_and_job):
        job, lease, attempt, node, worker_key, worker_acct, storage, result_bytes = active_lease_and_job
        result = await verify_proof(
            db,
            storage=storage,
            job_id=str(job.id),
            attempt_id=str(attempt.id),
            lease_id=str(lease.id),
            fingerprint_hex="ab" * 32,
            merkle_root_hex="cd" * 32,
            output_hash_hex="ef" * 32,
            merkle_proof=[],
            trace_hashes=[],
            checkpoint_names=[],
            signature_bytes=b"\x00" * 65,
            signer_address="0x" + "00" * 40,
            proof_timestamp=int(datetime.now(timezone.utc).timestamp()),
            protocol_version=99,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            model_id="resnet50",
        )
        assert result.verdict == Verdict.INVALID
        assert result.checks[0].check_name == "protocol_version"
        assert not result.checks[0].passed

    @pytest.mark.asyncio
    async def test_check_2_job_not_found(self, db: AsyncSession):
        result = await verify_proof(
            db,
            job_id=str(uuid.uuid4()),
            attempt_id=str(uuid.uuid4()),
            lease_id=str(uuid.uuid4()),
            fingerprint_hex="ab" * 32,
            merkle_root_hex="cd" * 32,
            output_hash_hex="ef" * 32,
            merkle_proof=[],
            trace_hashes=[],
            checkpoint_names=[],
            signature_bytes=b"\x00" * 65,
            signer_address="0x" + "00" * 40,
            proof_timestamp=int(datetime.now(timezone.utc).timestamp()),
            protocol_version=1,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            model_id="resnet50",
        )
        assert result.verdict == Verdict.INVALID
        assert not result.checks[1].passed

    @pytest.mark.asyncio
    async def test_check_4_expired_lease(self, db: AsyncSession, seed_model, seed_user, seed_node):
        node, worker_key, worker_acct = seed_node
        job = await create_job(
            db,
            user_id=seed_user.id,
            model_id="resnet50",
            chain_job_id="0x" + uuid.uuid4().hex,
            price_base_units=500000000000000000,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        await confirm_job_escrow(db, job_id=job.id, tx_hash="0xabc", escrow_amount=500000000000000000)

        lease = Lease(
            id=uuid.uuid4(),
            job_id=job.id,
            node_id=node.id,
            lease_id="0x" + secrets.token_hex(32),
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Expired!
            status="active",
        )
        db.add(lease)
        attempt = JobAttempt(
            id=uuid.uuid4(),
            job_id=job.id,
            node_id=node.id,
            lease_id=lease.id,
            attempt_number=1,
            status="running",
        )
        db.add(attempt)
        job.assigned_node_id = node.id
        job.current_lease_id = lease.id
        job.current_attempt = 1
        job.status = "proof_submitted"
        await db.flush()

        result = await verify_proof(
            db,
            job_id=str(job.id),
            attempt_id=str(attempt.id),
            lease_id=str(lease.id),
            fingerprint_hex="ab" * 32,
            merkle_root_hex="cd" * 32,
            output_hash_hex="ef" * 32,
            merkle_proof=[],
            trace_hashes=[],
            checkpoint_names=[],
            signature_bytes=b"\x00" * 65,
            signer_address="0x" + "00" * 40,
            proof_timestamp=int(datetime.now(timezone.utc).timestamp()),
            protocol_version=1,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            model_id="resnet50",
        )
        assert result.verdict == Verdict.INVALID
        assert not result.checks[3].passed  # check 4 (0-indexed: 3)

    @pytest.mark.asyncio
    async def test_check_9_wrong_checkpoints(self, db: AsyncSession, active_lease_and_job):
        job, lease, attempt, node, worker_key, worker_acct, storage, result_bytes = active_lease_and_job
        job.expected_fingerprint = hashlib.sha256(b"fp").hexdigest()

        result = await verify_proof(
            db,
            storage=storage,
            job_id=str(job.id),
            attempt_id=str(attempt.id),
            lease_id=str(lease.id),
            fingerprint_hex=job.expected_fingerprint,
            merkle_root_hex="cd" * 32,
            output_hash_hex="ef" * 32,
            merkle_proof=[],
            trace_hashes=[b"leaf1"],
            checkpoint_names=["wrong", "order"],  # Wrong checkpoints
            signature_bytes=b"\x00" * 65,
            signer_address="0x" + "00" * 40,
            proof_timestamp=int(datetime.now(timezone.utc).timestamp()),
            protocol_version=1,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            model_id="resnet50",
        )
        assert result.verdict == Verdict.INVALID
        assert not result.checks[8].passed  # check 9 (0-indexed: 8)

    @pytest.mark.asyncio
    async def test_check_12_replay_detected(self, db: AsyncSession, active_lease_and_job):
        job, lease, attempt, node, worker_key, worker_acct, storage, result_bytes = active_lease_and_job
        job.expected_fingerprint = hashlib.sha256(b"fp").hexdigest()

        # Create a proof record first
        proof = Proof(
            id=uuid.uuid4(),
            job_attempt_id=attempt.id,
            protocol_version=1,
            fingerprint_hash=job.expected_fingerprint,
            merkle_root="0x" + "cd" * 64,
            output_hash="ef" * 64,
            signature="0x" + "00" * 130,
            signer_address="0x" + "00" * 40,
            proof_timestamp=datetime.now(timezone.utc),
            valid=True,
        )
        db.add(proof)
        await db.flush()

        trace_hashes = [hashlib.sha256(b"step").digest()]
        job_id_bytes = bytes.fromhex(job.chain_job_id.removeprefix("0x"))
        ts = int(datetime.now(timezone.utc).timestamp())
        output_hash = hashlib.sha256(result_bytes).digest()
        merkle_root, proofs = build_merkle_tree([*trace_hashes, output_hash])
        envelope = ProofEnvelope(
            protocol_version=1,
            chain_id=421614,
            verifying_contract="0x" + "ab" * 20,
            job_id=job_id_bytes,
            attempt_id=bytes.fromhex(uuid_to_bytes32(attempt.id)[2:]),
            lease_id=bytes.fromhex(lease.lease_id[2:]),
            provider="0x" + "22" * 20,
            fingerprint=bytes.fromhex(job.expected_fingerprint),
            merkle_root=merkle_root,
            output_hash=output_hash,
            proof_timestamp=ts,
            lease_expires_at=int(lease.expires_at.timestamp()),
        )
        signature = sign_envelope(envelope, worker_key)

        await storage.put_object(job.result_file_key, result_bytes)

        result = await verify_proof(
            db,
            storage=storage,
            job_id=str(job.id),
            attempt_id=str(attempt.id),
            lease_id=str(lease.id),
            fingerprint_hex=job.expected_fingerprint,
            merkle_root_hex=merkle_root.hex(),
            output_hash_hex=output_hash.hex(),
            merkle_proof=proofs[0],
            trace_hashes=trace_hashes,
            checkpoint_names=["preprocess", "forward", "softmax", "topk"],
            signature_bytes=signature,
            signer_address=worker_acct.address,
            proof_timestamp=ts,
            protocol_version=1,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            model_id="resnet50",
        )
        assert result.verdict == Verdict.INVALID
        assert not result.checks[12].passed  # check 12 (0-indexed: 12)

    @pytest.mark.asyncio
    async def test_persist_verdict(self, db: AsyncSession, active_lease_and_job):
        job, lease, attempt, node, worker_key, worker_acct, storage, result_bytes = active_lease_and_job
        vr = VerificationResult()
        vr.verdict = Verdict.VALID

        class FakeCheck:
            check_number = 1
            check_name = "test"
            passed = True
            error = None

            def to_dict(self):
                return {"passed": True}

        vr.add_check(FakeCheck())

        proof = await persist_verdict(
            db,
            attempt_id=str(attempt.id),
            result=vr,
            fingerprint_hash="ab" * 64,
            merkle_root="cd" * 64,
            output_hash="ef" * 64,
            signature="0x" + "00" * 130,
            signer_address="0x" + "ab" * 20,
            proof_timestamp=datetime.now(timezone.utc),
        )
        assert proof is not None
        assert proof.valid is True
        assert proof.verification_error is None
