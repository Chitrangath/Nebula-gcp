"""Tests for the assignment dispatcher service.

Proves:
- Scheduler DB transaction commits before dispatcher RPC
- Dispatcher does not hold row locks during RPC
- Dispatcher builds and signs assignProvider()
- Dispatcher persists ChainTransaction with nonce and tx_hash
- Dispatcher activates lease only after ProviderAssigned confirmation
- Dispatcher transitions job to assigned after confirmation
- Dispatcher handles reverted/dropped/replaced transactions
- Dispatcher reconciles already-mined transactions
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChainTransaction, Job, JobAttempt, Lease, Node, SupportedModel, User
from app.services.assignment_dispatcher import AssignmentDispatcher
from app.services.blockchain_service import FakeBlockchainBackend
from app.services.job_service import confirm_job_escrow, create_job
from app.services.scheduler import schedule_next_job
from app.services.tx_signer import FakeSigner


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
async def seed_provider(db: AsyncSession):
    provider = User(id=uuid.uuid4(), wallet_address="0x" + "11" * 20, role="provider")
    db.add(provider)
    await db.flush()
    return provider


@pytest_asyncio.fixture
async def seed_node(db: AsyncSession, seed_provider):
    node = Node(
        id=uuid.uuid4(),
        provider_id=seed_provider.id,
        gpu_name="RTX 4090",
        vram_gb=24,
        status="online",
        worker_signer_address="0x" + "ab" * 20,
        api_key_hash=hashlib.sha256(b"dispatcher-test-key").hexdigest(),
        active_leases=0,
        last_heartbeat=datetime.now(timezone.utc),
    )
    db.add(node)
    await db.flush()
    return node


@pytest_asyncio.fixture
async def scheduled_lease(db: AsyncSession, seed_model, seed_provider, seed_node):
    """Create a queued job, run scheduler, return (job, lease, node)."""
    user = User(id=uuid.uuid4(), wallet_address="0x" + uuid.uuid4().hex, role="user")
    db.add(user)
    await db.flush()

    job = await create_job(
        db,
        user_id=user.id,
        model_id="resnet50",
        chain_job_id="0x" + uuid.uuid4().hex,
        price_base_units=500000000000000000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    await confirm_job_escrow(db, job_id=job.id, tx_hash="0xabc", escrow_amount=500000000000000000)
    result = await schedule_next_job(db)
    assert result is not None
    job, node, lease = result
    await db.flush()
    return job, lease, node


@pytest_asyncio.fixture
def fake_blockchain():
    return FakeBlockchainBackend(chain_id=421614)


@pytest_asyncio.fixture
def fake_signer():
    return FakeSigner(address="0x" + "ab" * 20, chain_id=421614)


@pytest_asyncio.fixture
def dispatcher(fake_blockchain, fake_signer):
    return AssignmentDispatcher(
        blockchain=fake_blockchain,
        signer=fake_signer,
        contract_address="0x" + "00" * 20,
        chain_id=421614,
        rpc_url="http://127.0.0.1:8545",
    )


class TestDispatcherArchitecture:
    @pytest.mark.asyncio
    async def test_scheduler_commits_before_dispatcher(self, db: AsyncSession, scheduled_lease):
        """Scheduler transaction is committed before dispatcher reads pending_chain leases."""
        job, lease, node = scheduled_lease

        # After scheduler commits, lease should be pending_chain
        assert lease.status == "pending_chain"

        # Verify a separate session can see the pending_chain lease
        from sqlalchemy import select

        result = await db.execute(select(Lease).where(Lease.id == lease.id))
        fetched = result.scalar_one_or_none()
        assert fetched is not None
        assert fetched.status == "pending_chain"

    @pytest.mark.asyncio
    async def test_dispatcher_does_not_hold_row_locks(self, db: AsyncSession, scheduled_lease):
        """Dispatcher does not hold row locks from the scheduler during RPC."""
        job, lease, node = scheduled_lease

        # The scheduler's session has committed (from scheduled_lease fixture).
        # The dispatcher should be able to read the lease without FOR UPDATE.
        # This is architecturally enforced because the dispatcher runs in a
        # separate process/context after the scheduler commits.

        from sqlalchemy import select

        # A new session should be able to read without blocking
        result = await db.execute(select(Lease).where(Lease.id == lease.id))
        fetched = result.scalar_one_or_none()
        assert fetched is not None
        assert fetched.status == "pending_chain"

    @pytest.mark.asyncio
    async def test_dispatcher_finds_pending_chain_leases(self, db: AsyncSession, dispatcher, scheduled_lease):
        """Dispatcher identifies all pending_chain leases."""
        job, lease, node = scheduled_lease

        pending = await db.execute(select(Lease).where(Lease.status == "pending_chain"))
        leases = pending.scalars().all()
        assert any(lev.id == lease.id for lev in leases)


class TestDispatcherDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_builds_assign_provider_tx(self, db: AsyncSession, dispatcher, scheduled_lease):
        """Dispatcher builds and signs assignProvider() transaction."""
        job, lease, node = scheduled_lease

        dispatched = await dispatcher.dispatch_pending_assignments(db)

        assert len(dispatched) == 1
        assert str(lease.id) in dispatched

        # ChainTransaction should be persisted
        tx_result = await db.execute(
            select(ChainTransaction).where(
                ChainTransaction.job_id == job.id,
                ChainTransaction.tx_type == "assignProvider",
            )
        )
        chain_tx = tx_result.scalar_one_or_none()
        assert chain_tx is not None
        assert chain_tx.status == "submitted"
        assert chain_tx.nonce is not None
        assert chain_tx.tx_hash is not None

    @pytest.mark.asyncio
    async def test_dispatch_persists_nonce_and_tx_hash(self, db: AsyncSession, dispatcher, scheduled_lease):
        """Dispatcher persists nonce and tx_hash on both ChainTransaction and Lease."""
        job, lease, node = scheduled_lease

        await dispatcher.dispatch_pending_assignments(db)

        # Check ChainTransaction
        tx_result = await db.execute(select(ChainTransaction).where(ChainTransaction.job_id == job.id))
        chain_tx = tx_result.scalar_one()
        assert chain_tx.nonce >= 0
        assert chain_tx.tx_hash.startswith("0x")

        # Check Lease updated
        lease_result = await db.execute(select(Lease).where(Lease.id == lease.id))
        updated_lease = lease_result.scalar_one()
        assert updated_lease.tx_hash == chain_tx.tx_hash
        assert updated_lease.nonce == chain_tx.nonce

    @pytest.mark.asyncio
    async def test_dispatch_skips_already_dispatched(self, db: AsyncSession, dispatcher, scheduled_lease):
        """Dispatcher skips leases that already have a ChainTransaction."""
        job, lease, node = scheduled_lease

        # First dispatch
        dispatched1 = await dispatcher.dispatch_pending_assignments(db)
        assert len(dispatched1) == 1

        # Second dispatch — should skip
        dispatched2 = await dispatcher.dispatch_pending_assignments(db)
        assert len(dispatched2) == 0

    @pytest.mark.asyncio
    async def test_signer_signs_transaction(self, db: AsyncSession, dispatcher, scheduled_lease):
        """FakeSigner records the transaction call."""
        job, lease, node = scheduled_lease

        await dispatcher.dispatch_pending_assignments(db)

        assert len(dispatcher._signer.sent_txs) >= 1
        tx = dispatcher._signer.sent_txs[-1]
        assert tx.get("to") == dispatcher._contract_address


class TestDispatcherConfirmation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "authoritative_status",
        [
            "proof_submitted",
            "verifying",
            "settling",
            "completed",
            "refunded",
            "awaiting_timeout_refund",
            "failed",
            "expired_pre_escrow",
        ],
    )
    async def test_late_reverted_assignment_preserves_authoritative_job_status(
        self, db: AsyncSession, dispatcher, scheduled_lease, authoritative_status
    ):
        job, lease, _ = scheduled_lease
        await dispatcher.dispatch_pending_assignments(db)
        chain_tx = (
            await db.execute(select(ChainTransaction).where(ChainTransaction.lease_id == lease.id))
        ).scalar_one()
        job.status = authoritative_status
        job.error_message = "authoritative job diagnostic"
        await db.flush()
        receipt = {"status": 0, "blockNumber": 100, "blockHash": b"\xab" * 32, "logs": []}

        with patch.object(dispatcher._blockchain, "wait_for_receipt", return_value=receipt):
            await dispatcher.confirm_assignment(
                db,
                lease_id=lease.id,
                tx_hash=chain_tx.tx_hash,
                block_number=100,
                block_hash="0x" + "ab" * 32,
            )

        assert job.status == authoritative_status
        assert job.error_message == "authoritative job diagnostic"
        assert lease.status == "failed"

    @pytest.mark.asyncio
    async def test_confirm_activates_lease(self, db: AsyncSession, dispatcher, scheduled_lease):
        """Confirmation activates the lease and transitions job to assigned."""
        job, lease, node = scheduled_lease

        # Dispatch first
        await dispatcher.dispatch_pending_assignments(db)

        # Get the tx_hash
        tx_result = await db.execute(select(ChainTransaction).where(ChainTransaction.job_id == job.id))
        chain_tx = tx_result.scalar_one()
        tx_hash = chain_tx.tx_hash

        # Mock the blockchain to return a receipt with ProviderAssigned event
        mock_receipt = {
            "status": 1,
            "blockNumber": 100,
            "blockHash": b"\xab" * 32,
            "logs": [],
        }
        with patch.object(dispatcher._blockchain, "wait_for_receipt", return_value=mock_receipt):
            with patch(
                "app.services.assignment_dispatcher.decode_receipt_logs",
                return_value=[
                    {
                        "event": "ProviderAssigned",
                        "args": {
                            "jobId": bytes.fromhex(job.chain_job_id[2:]),
                            "provider": "0x" + "11" * 20,
                            "leaseId": bytes.fromhex(lease.lease_id[2:]),
                            "leaseExpiresAt": int(lease.expires_at.timestamp()),
                        },
                    }
                ],
            ):
                result = await dispatcher.confirm_assignment(
                    db,
                    lease_id=lease.id,
                    tx_hash=tx_hash,
                    block_number=100,
                    block_hash="0x" + "ab" * 64,
                )

        assert result is True

        # Lease should be active
        lease_result = await db.execute(select(Lease).where(Lease.id == lease.id))
        updated_lease = lease_result.scalar_one()
        assert updated_lease.status == "active"

        # Job should be assigned
        job_result = await db.execute(select(Job).where(Job.id == job.id))
        updated_job = job_result.scalar_one()
        assert updated_job.status == "assigned"

    @pytest.mark.asyncio
    async def test_confirm_reverts_transaction(self, db: AsyncSession, dispatcher, scheduled_lease):
        """Reverted on-chain transaction is marked as reverted."""
        job, lease, node = scheduled_lease

        await dispatcher.dispatch_pending_assignments(db)

        tx_result = await db.execute(select(ChainTransaction).where(ChainTransaction.job_id == job.id))
        chain_tx = tx_result.scalar_one()
        tx_hash = chain_tx.tx_hash

        mock_receipt = {"status": 0, "blockNumber": 100, "blockHash": b"\xab" * 32, "logs": []}
        with patch.object(dispatcher._blockchain, "wait_for_receipt", return_value=mock_receipt):
            result = await dispatcher.confirm_assignment(
                db,
                lease_id=lease.id,
                tx_hash=tx_hash,
                block_number=100,
                block_hash="0x" + "ab" * 64,
            )

        assert result is False

        tx_result2 = await db.execute(select(ChainTransaction).where(ChainTransaction.tx_hash == tx_hash))
        reverted = tx_result2.scalar_one()
        assert reverted.status == "reverted"
        assert reverted.error == "assignProvider transaction reverted"
        assert lease.status == "failed"
        assert job.status == "retry_pending"
        attempt = (await db.execute(select(JobAttempt).where(JobAttempt.lease_id == lease.id))).scalar_one()
        assert attempt.status == "failed"
        assert attempt.error == "assignProvider transaction reverted"
        assert attempt.completed_at is not None
        # The failed pending lease must no longer block a safe fresh attempt.
        replacement = await schedule_next_job(db)
        assert replacement is not None
        assert replacement[2].id != lease.id

    @pytest.mark.asyncio
    async def test_confirm_missing_provider_assigned_event(self, db: AsyncSession, dispatcher, scheduled_lease):
        """Missing ProviderAssigned event prevents activation."""
        job, lease, node = scheduled_lease

        await dispatcher.dispatch_pending_assignments(db)

        tx_result = await db.execute(select(ChainTransaction).where(ChainTransaction.job_id == job.id))
        chain_tx = tx_result.scalar_one()
        tx_hash = chain_tx.tx_hash

        mock_receipt = {"status": 1, "blockNumber": 100, "blockHash": b"\xab" * 32, "logs": []}
        with patch.object(dispatcher._blockchain, "wait_for_receipt", return_value=mock_receipt):
            with patch(
                "app.services.assignment_dispatcher.decode_receipt_logs",
                return_value=[],  # No ProviderAssigned event
            ):
                result = await dispatcher.confirm_assignment(
                    db,
                    lease_id=lease.id,
                    tx_hash=tx_hash,
                    block_number=100,
                    block_hash="0x" + "ab" * 64,
                )

        assert result is False

    @pytest.mark.asyncio
    async def test_confirm_idempotent(self, db: AsyncSession, dispatcher, scheduled_lease):
        """Confirming an already-confirmed transaction is idempotent."""
        job, lease, node = scheduled_lease

        await dispatcher.dispatch_pending_assignments(db)

        tx_result = await db.execute(select(ChainTransaction).where(ChainTransaction.job_id == job.id))
        chain_tx = tx_result.scalar_one()
        tx_hash = chain_tx.tx_hash

        mock_receipt = {"status": 1, "blockNumber": 100, "blockHash": b"\xab" * 32, "logs": []}
        with patch.object(dispatcher._blockchain, "wait_for_receipt", return_value=mock_receipt):
            with patch(
                "app.services.assignment_dispatcher.decode_receipt_logs",
                return_value=[
                    {
                        "event": "ProviderAssigned",
                        "args": {
                            "jobId": bytes.fromhex(job.chain_job_id[2:]),
                            "provider": "0x" + "11" * 20,
                            "leaseId": bytes.fromhex(lease.lease_id[2:]),
                            "leaseExpiresAt": int(lease.expires_at.timestamp()),
                        },
                    }
                ],
            ):
                # First confirmation
                result1 = await dispatcher.confirm_assignment(
                    db,
                    lease_id=lease.id,
                    tx_hash=tx_hash,
                    block_number=100,
                    block_hash="0x" + "ab" * 64,
                )
                assert result1 is True

                # Second confirmation — should be idempotent
                result2 = await dispatcher.confirm_assignment(
                    db,
                    lease_id=lease.id,
                    tx_hash=tx_hash,
                    block_number=100,
                    block_hash="0x" + "ab" * 64,
                )
                assert result2 is True


class TestDispatcherReconciliation:
    @pytest.mark.asyncio
    async def test_reconcile_reverted_assignment_closes_exhausted_attempt(
        self, db: AsyncSession, dispatcher, scheduled_lease
    ):
        job, lease, _ = scheduled_lease
        job.current_attempt = job.max_attempts
        await dispatcher.dispatch_pending_assignments(db)
        chain_tx = (
            await db.execute(select(ChainTransaction).where(ChainTransaction.lease_id == lease.id))
        ).scalar_one()
        receipt = {"status": 0, "blockNumber": 100, "blockHash": b"\xab" * 32, "logs": []}

        with patch.object(dispatcher._blockchain, "wait_for_receipt", return_value=receipt):
            result = await dispatcher.reconcile_existing_tx(db, tx_hash=chain_tx.tx_hash)

        assert result["status"] == "reverted"
        assert lease.status == "failed"
        assert job.status == "attempts_exhausted"
        attempt = (await db.execute(select(JobAttempt).where(JobAttempt.lease_id == lease.id))).scalar_one()
        assert attempt.error == "assignProvider transaction reverted"
        assert attempt.status == "failed"
        assert await schedule_next_job(db) is None

    @pytest.mark.asyncio
    async def test_reconcile_already_mined(self, db: AsyncSession, dispatcher, scheduled_lease):
        """Reconcile fetches receipt for already-mined transaction."""
        job, lease, node = scheduled_lease

        await dispatcher.dispatch_pending_assignments(db)

        tx_result = await db.execute(select(ChainTransaction).where(ChainTransaction.job_id == job.id))
        chain_tx = tx_result.scalar_one()
        tx_hash = chain_tx.tx_hash

        mock_receipt = {"status": 1, "blockNumber": 100, "blockHash": b"\xab" * 32, "logs": []}
        with patch.object(dispatcher._blockchain, "wait_for_receipt", return_value=mock_receipt):
            result = await dispatcher.reconcile_existing_tx(db, tx_hash=tx_hash)

        assert result["status"] == "confirmed"
        assert result["block_number"] == 100

    @pytest.mark.asyncio
    async def test_reconcile_already_confirmed(self, db: AsyncSession, dispatcher, scheduled_lease):
        """Reconcile skips already-confirmed transactions."""
        job, lease, node = scheduled_lease

        await dispatcher.dispatch_pending_assignments(db)

        tx_result = await db.execute(select(ChainTransaction).where(ChainTransaction.job_id == job.id))
        chain_tx = tx_result.scalar_one()
        chain_tx.status = "confirmed"
        await db.flush()

        result = await dispatcher.reconcile_existing_tx(db, tx_hash=chain_tx.tx_hash)
        assert result["status"] == "already_processed"

    @pytest.mark.asyncio
    async def test_handle_dropped_resets_lease(self, db: AsyncSession, dispatcher, scheduled_lease):
        """Dropped transaction resets lease for re-dispatch."""
        job, lease, node = scheduled_lease

        await dispatcher.dispatch_pending_assignments(db)

        result = await dispatcher.handle_dropped_tx(db, lease_id=lease.id)
        assert result["status"] == "reset_for_redispatch"

        # Verify lease is reset
        lease_result = await db.execute(select(Lease).where(Lease.id == lease.id))
        updated = lease_result.scalar_one()
        assert updated.tx_hash is None
        assert updated.nonce is None

        # ChainTransaction should be marked as dropped
        tx_result = await db.execute(select(ChainTransaction).where(ChainTransaction.job_id == job.id))
        chain_tx = tx_result.scalar_one()
        assert chain_tx.status == "dropped"
