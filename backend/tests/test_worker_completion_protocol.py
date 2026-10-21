"""Worker result/proof protocol regressions."""

import base64
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from eth_account import Account
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.main import app
from app.models import Job, JobAttempt, Lease, Node, SupportedModel, User
from app.services.eip712 import ProofEnvelope, sign_envelope
from app.services.merkle import build_merkle_tree
from app.services.storage import InMemoryStorage, make_result_key
from app.utils import uuid_to_bytes32


@pytest.mark.asyncio
async def test_result_hash_never_overwrites_input_and_completion_queues_full_envelope(db: AsyncSession, monkeypatch):
    worker = Account.create()
    api_key = "worker-api-key"
    user = User(id=uuid.uuid4(), wallet_address="0x" + "11" * 20, role="user")
    provider = User(id=uuid.uuid4(), wallet_address="0x" + "22" * 20, role="provider")
    model = SupportedModel(id="resnet50", name="R", price_base_units=50_000)
    node = Node(
        id=uuid.uuid4(),
        provider_id=provider.id,
        status="online",
        vram_gb=24,
        worker_signer_address=worker.address,
        api_key_hash=hashlib.sha256(api_key.encode()).hexdigest(),
    )
    job = Job(
        id=uuid.uuid4(),
        user_id=user.id,
        model_id=model.id,
        chain_job_id="",
        status="running",
        input_hash=hashlib.sha256(b"input").hexdigest(),
        expected_fingerprint=hashlib.sha256(b"fingerprint").hexdigest(),
        price_base_units=50_000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=24),
        assigned_node_id=node.id,
        current_attempt=1,
    )
    job.chain_job_id = uuid_to_bytes32(job.id)
    lease = Lease(
        id=uuid.uuid4(),
        job_id=job.id,
        node_id=node.id,
        lease_id="0x" + "33" * 32,
        status="active",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    attempt = JobAttempt(
        id=uuid.uuid4(), job_id=job.id, node_id=node.id, lease_id=lease.id, attempt_number=1, status="running"
    )
    job.current_lease_id = lease.id
    db.add_all([user, provider, model, node, job, lease, attempt])
    await db.flush()

    storage = InMemoryStorage()
    app.state.storage = storage
    monkeypatch.setattr(settings, "CHAIN_ID", 31337)
    monkeypatch.setattr(settings, "NEBULA_PAYMENT_CONTRACT", "0x" + "ab" * 20)
    result_bytes = b'{"class":7,"score":"0.950000"}\n'
    output_hash = hashlib.sha256(result_bytes).digest()
    trace = [hashlib.sha256(name.encode()).digest() for name in ["preprocess", "forward", "softmax", "topk"]]
    merkle_root, _ = build_merkle_tree([*trace, output_hash])
    proof_timestamp = int(datetime.now(timezone.utc).timestamp())
    envelope = ProofEnvelope(
        protocol_version=1,
        chain_id=31337,
        verifying_contract="0x" + "ab" * 20,
        job_id=bytes.fromhex(job.chain_job_id[2:]),
        attempt_id=bytes.fromhex(uuid_to_bytes32(attempt.id)[2:]),
        lease_id=bytes.fromhex(lease.lease_id[2:]),
        provider=provider.wallet_address,
        fingerprint=bytes.fromhex(job.expected_fingerprint),
        merkle_root=merkle_root,
        output_hash=output_hash,
        proof_timestamp=proof_timestamp,
        lease_expires_at=int(lease.expires_at.timestamp()),
    )
    key = make_result_key(str(job.id), str(attempt.id))
    headers = {"X-API-Key": api_key}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        uploaded = await client.post(
            f"/v1/worker/leases/{lease.id}/result-upload",
            headers=headers,
            json={"result_file_key": key, "result_bytes_base64": base64.b64encode(result_bytes).decode()},
        )
        assert uploaded.status_code == 200, uploaded.text
        original_input_hash = job.input_hash
        payload = {
            "protocol_version": 1,
            "chain_id": 31337,
            "verifying_contract": envelope.verifying_contract,
            "job_id": "0x" + envelope.job_id.hex(),
            "attempt_id": "0x" + envelope.attempt_id.hex(),
            "lease_id": "0x" + envelope.lease_id.hex(),
            "provider": envelope.provider,
            "fingerprint": "0x" + envelope.fingerprint.hex(),
            "merkle_root": "0x" + envelope.merkle_root.hex(),
            "output_hash": "0x" + envelope.output_hash.hex(),
            "proof_timestamp": proof_timestamp,
            "lease_expires_at": envelope.lease_expires_at,
            "checkpoint_names": ["preprocess", "forward", "softmax", "topk"],
            "trace_hashes": ["0x" + value.hex() for value in trace],
            "signature": "0x" + sign_envelope(envelope, worker.key).hex(),
            "result_file_key": key,
        }
        wrong_domain = await client.post(
            f"/v1/worker/leases/{lease.id}/complete",
            headers=headers,
            json={**payload, "chain_id": 1},
        )
        assert wrong_domain.status_code == 409
        malformed_trace = await client.post(
            f"/v1/worker/leases/{lease.id}/complete",
            headers=headers,
            json={**payload, "trace_hashes": ["not-a-hash"]},
        )
        assert malformed_trace.status_code == 422
        expired_timestamp = await client.post(
            f"/v1/worker/leases/{lease.id}/complete",
            headers=headers,
            json={**payload, "proof_timestamp": envelope.lease_expires_at + 1},
        )
        assert expired_timestamp.status_code == 409
        zero_root = await client.post(
            f"/v1/worker/leases/{lease.id}/complete",
            headers=headers,
            json={**payload, "merkle_root": "0x" + "00" * 32},
        )
        assert zero_root.status_code == 422
        completed = await client.post(
            f"/v1/worker/leases/{lease.id}/complete",
            headers=headers,
            json=payload,
        )
        conflicting_repeat = await client.post(
            f"/v1/worker/leases/{lease.id}/complete",
            headers=headers,
            json={**payload, "merkle_root": "0x" + "44" * 32},
        )
    assert completed.status_code == 202, completed.text
    assert conflicting_repeat.status_code == 409
    assert job.input_hash == original_input_hash
    assert job.result_output_hash == output_hash.hex()
    assert job.status == "verifying"
