"""Tests for the jobs API router (PRD v3.1 §16)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.main import app
from app.models import (
    BlockchainEvent,
    ChainTransaction,
    Job,
    JobAttempt,
    Lease,
    Node,
    Payment,
    Proof,
    SupportedModel,
)
from tests.conftest import seed_authed_user
from tests.vectors import PNG_1X1


async def create_job_request(client: AsyncClient, token: str) -> Response:
    return await client.post(
        "/v1/jobs",
        data={
            "model_id": "resnet50",
            "deadline": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
        files={"input_file": ("input.png", PNG_1X1, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest_asyncio.fixture
async def seed_model(db: AsyncSession) -> SupportedModel:
    model = SupportedModel(
        id="resnet50",
        name="ResNet-50",
        framework="pytorch",
        vram_required_gb=8,
        price_base_units=500000000000000000,
        model_version="1.0",
        preprocessing_version="resnet50-v1",
        model_hash_sha256="ab" * 32,
        max_input_size_mb=1,
        input_type="image",
        supported_formats=["jpg", "png"],
    )
    db.add(model)
    await db.flush()
    return model


@pytest.mark.asyncio
async def test_create_job_endpoint(db: AsyncSession, seed_model):
    user_id, token = await seed_authed_user(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await create_job_request(client, token)
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_id"] == "resnet50"
    assert data["status"] == "pending_blockchain"
    assert data["chain_job_id"] is not None


@pytest.mark.asyncio
async def test_list_jobs_empty(db: AsyncSession):
    user_id, token = await seed_authed_user(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/v1/jobs",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["jobs"] == []


@pytest.mark.asyncio
async def test_get_job_not_found(db: AsyncSession):
    user_id, token = await seed_authed_user(db)
    fake_id = str(uuid.uuid4())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/v1/jobs/{fake_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_job_detail_exposes_authoritative_chain_and_payment_evidence(db: AsyncSession, seed_model):
    user_id, token = await seed_authed_user(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await create_job_request(client, token)
        job_id = uuid.UUID(created.json()["id"])
        chain_instance = "0x" + "99" * 32
        for index, kind in enumerate(("createJob", "assignProvider", "submitProof", "verifyJob"), start=1):
            db.add(
                ChainTransaction(
                    chain_id=settings.CHAIN_ID,
                    chain_instance_id=chain_instance,
                    contract_address=settings.NEBULA_PAYMENT_CONTRACT,
                    job_id=job_id,
                    tx_hash="0x" + f"{index:02x}" * 32,
                    tx_type=kind,
                    from_address="0x" + "11" * 20,
                    to_address=settings.NEBULA_PAYMENT_CONTRACT,
                    block_number=322_000_000 + index,
                    status="confirmed",
                    idempotency_key=f"evidence-{kind}",
                )
            )
        db.add(
            Payment(
                job_id=job_id,
                user_id=user_id,
                amount_base_units=50_000,
                payment_type="provider_credit",
                status="credited",
                blockchain_tx_hash="0x" + "04" * 32,
            )
        )
        db.add(
            ChainTransaction(
                chain_id=1,
                chain_instance_id="0x" + "77" * 32,
                contract_address="0x" + "de" * 20,
                job_id=job_id,
                tx_hash="0x" + "ff" * 32,
                tx_type="createJob",
                from_address="0x" + "11" * 20,
                to_address="0x" + "de" * 20,
                block_number=99_999_999,
                status="finalized",
                created_at=datetime.now(timezone.utc) + timedelta(days=1),
                idempotency_key="decoy-chain-escrow",
            )
        )
        db.add(
            BlockchainEvent(
                chain_id=1,
                chain_instance_id="0x" + "77" * 32,
                contract_address="0x" + "de" * 20,
                transaction_hash="0x" + "fe" * 32,
                log_index=0,
                block_number=99_999_999,
                block_hash="0x" + "fd" * 32,
                event_name="TimeoutRefundCredited",
                job_id=job_id,
                event_data={"amount": 50_000},
                confirmation_status="finalized",
            )
        )
        await db.flush()

        response = await client.get(f"/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["chain_id"] == settings.CHAIN_ID
    assert body["escrow_transaction"] == {
        "hash": "0x" + "01" * 32,
        "status": "confirmed",
        "chain_id": settings.CHAIN_ID,
        "block_number": 322_000_001,
    }
    assert body["assignment_transaction"]["block_number"] == 322_000_002
    assert body["proof_transaction"]["block_number"] == 322_000_003
    assert body["settlement_transaction"]["block_number"] == 322_000_004
    assert body["provider_payment_credit_status"] == "credited"
    assert body["on_chain_state"] is None


@pytest.mark.asyncio
async def test_job_detail_exposes_sanitized_attempt_history(db: AsyncSession, seed_model):
    user_id, token = await seed_authed_user(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await create_job_request(client, token)
        job_id = uuid.UUID(created.json()["id"])
        job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one()
        first = Node(
            provider_id=user_id,
            gpu_name="GPU B",
            vram_gb=4,
            status="offline",
            api_key_hash="aa" * 32,
        )
        second = Node(
            provider_id=user_id,
            gpu_name="GPU C",
            vram_gb=8,
            status="online",
            api_key_hash="bb" * 32,
        )
        db.add_all([first, second])
        await db.flush()
        first_lease = Lease(
            job_id=job_id,
            node_id=first.id,
            lease_id="0x" + "10" * 32,
            expires_at=datetime.now(timezone.utc),
            status="failed",
        )
        second_lease = Lease(
            job_id=job_id,
            node_id=second.id,
            lease_id="0x" + "20" * 32,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            status="completed",
        )
        db.add_all([first_lease, second_lease])
        await db.flush()
        db.add_all(
            [
                JobAttempt(
                    job_id=job_id,
                    node_id=first.id,
                    lease_id=first_lease.id,
                    attempt_number=1,
                    status="failed",
                    error="lease_expired",
                ),
                JobAttempt(
                    job_id=job_id,
                    node_id=second.id,
                    lease_id=second_lease.id,
                    attempt_number=2,
                    status="completed",
                ),
            ]
        )
        job.assigned_node_id = second.id
        job.current_lease_id = second_lease.id
        await db.commit()

        response = await client.get(f"/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["attempt_history"] == [
        {"attempt_number": 1, "node_id": str(first.id), "status": "failed"},
        {"attempt_number": 2, "node_id": str(second.id), "status": "completed"},
    ]
    assert "lease_expired" not in response.text


@pytest.mark.asyncio
async def test_job_detail_distinguishes_expected_and_submitted_proof_fingerprints(db: AsyncSession, seed_model):
    user_id, token = await seed_authed_user(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await create_job_request(client, token)
        job_id = uuid.UUID(created.json()["id"])
        job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one()
        job.expected_fingerprint = "11" * 32
        node = Node(
            provider_id=user_id,
            gpu_name="Test GPU",
            vram_gb=8,
            status="online",
            api_key_hash="aa" * 32,
        )
        db.add(node)
        await db.flush()
        lease = Lease(
            job_id=job_id,
            node_id=node.id,
            lease_id="0x" + "22" * 32,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            status="active",
        )
        db.add(lease)
        await db.flush()
        attempt = JobAttempt(
            job_id=job_id,
            node_id=node.id,
            lease_id=lease.id,
            attempt_number=1,
            status="completed",
        )
        db.add(attempt)
        await db.flush()
        db.add(
            Proof(
                job_attempt_id=attempt.id,
                fingerprint_hash="33" * 32,
                merkle_root="0x" + "44" * 32,
                output_hash="55" * 32,
                signature="0x" + "66" * 65,
                signer_address="0x" + "77" * 20,
                proof_timestamp=datetime.now(timezone.utc),
                valid=False,
                verification_status="verified",
            )
        )
        await db.flush()

        response = await client.get(f"/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["fingerprint"] == "11" * 32
    assert body["proof_fingerprint"] == "33" * 32
    assert body["proof_verification_status"] == "invalid"


@pytest.mark.asyncio
async def test_job_detail_derives_refund_transaction_from_canonical_chain_event(db: AsyncSession, seed_model):
    user_id, token = await seed_authed_user(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await create_job_request(client, token)
        job_id = uuid.UUID(created.json()["id"])
        job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one()
        job.status = "refunded"
        chain_instance = "0x" + "88" * 32
        db.add(
            ChainTransaction(
                chain_id=settings.CHAIN_ID,
                chain_instance_id=chain_instance,
                contract_address=settings.NEBULA_PAYMENT_CONTRACT,
                job_id=job_id,
                tx_hash="0x" + "10" * 32,
                tx_type="createJob",
                from_address="0x" + "11" * 20,
                to_address=settings.NEBULA_PAYMENT_CONTRACT,
                block_number=322_000_010,
                status="finalized",
                idempotency_key="refund-escrow",
            )
        )
        refund_hash = "0x" + "20" * 32
        db.add(
            BlockchainEvent(
                chain_id=settings.CHAIN_ID,
                chain_instance_id=chain_instance,
                contract_address=settings.NEBULA_PAYMENT_CONTRACT,
                transaction_hash=refund_hash,
                log_index=0,
                block_number=322_000_020,
                block_hash="0x" + "30" * 32,
                event_name="TimeoutRefundCredited",
                job_id=job_id,
                event_data={"amount": 50_000},
                confirmation_status="finalized",
            )
        )
        db.add(
            Payment(
                job_id=job_id,
                user_id=user_id,
                amount_base_units=50_000,
                payment_type="user_refund",
                status="credited",
                blockchain_tx_hash=refund_hash,
            )
        )
        await db.flush()

        response = await client.get(f"/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["refund_transaction"] == {
        "hash": refund_hash,
        "status": "finalized",
        "chain_id": settings.CHAIN_ID,
        "block_number": 322_000_020,
    }


@pytest.mark.asyncio
async def test_create_job_unauthorized(db: AsyncClient):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/jobs",
            json={
                "model_id": "resnet50",
                "price_base_units": "500000000000000000",
                "deadline": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            },
        )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_confirm_escrow(db: AsyncSession, seed_model):
    """Client-supplied escrow authority is rejected by the strict schema."""
    from app.services.blockchain_service import FakeBlockchainBackend

    app.state.blockchain = FakeBlockchainBackend()
    user_id, token = await seed_authed_user(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a job first
        create_resp = await create_job_request(client, token)
        job_id = create_resp.json()["id"]

        # Confirm escrow
        resp = await client.post(
            f"/v1/jobs/{job_id}/confirm-escrow",
            json={
                "tx_hash": "0xabcdef1234567890",
                "escrow_amount": "500000000000000000",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_confirm_escrow_not_your_job(db: AsyncSession, seed_model):
    from app.services.blockchain_service import FakeBlockchainBackend

    app.state.blockchain = FakeBlockchainBackend()
    user_id, token = await seed_authed_user(db)
    other_id, other_token = await seed_authed_user(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await create_job_request(client, token)
        job_id = create_resp.json()["id"]

        resp = await client.post(
            f"/v1/jobs/{job_id}/confirm-escrow",
            json={
                "tx_hash": "0xabcdef1234567890",
            },
            headers={"Authorization": f"Bearer {other_token}"},
        )
    assert resp.status_code == 403
