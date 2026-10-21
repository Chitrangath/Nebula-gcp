"""Tests for blockchain event durability, reorg behavior, and backfill (§6).

Tests:
- Backfill from persisted checkpoint
- Restart from checkpoint
- Overlapping backfill without duplicate events
- Confirmation progression
- Non-final event reorg (block hash mismatch)
- Replacement event ingestion
- Chain success / DB failure recovery
- Repeated reconciliation idempotency
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BlockchainEvent, SupportedModel, User
from app.services.blockchain_events import (
    backfill_events,
    confirm_event,
    confirm_events_at_block,
    finalize_event,
    get_checkpoint,
    get_unconfirmed_events,
    handle_reorg,
    reconcile_job_state,
    record_event,
    recover_from_db_failure,
    replace_event,
)


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


class TestEventDurability:
    @pytest.mark.asyncio
    async def test_record_event_idempotent(self, db: AsyncSession):
        """Same event recorded twice returns existing, no duplicate."""
        ev = await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=100,
            block_hash="0x" + "ef" * 32,
            event_name="JobCreated",
            event_data={"key": "val"},
        )
        ev2 = await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=100,
            block_hash="0x" + "ef" * 32,
            event_name="JobCreated",
            event_data={"key": "val"},
        )
        assert ev2.id == ev.id

    @pytest.mark.asyncio
    async def test_checkpoint_management(self, db: AsyncSession):
        """Checkpoint returns max block number."""
        await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=100,
            block_hash="0x" + "ef" * 32,
            event_name="JobCreated",
            event_data={},
        )
        await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd2" * 32,
            log_index=0,
            block_number=200,
            block_hash="0x" + "ef" * 32,
            event_name="JobCreated",
            event_data={},
        )

        cp = await get_checkpoint(db, 421614, "0x" + "ab" * 20)
        assert cp["last_block"] == 200

    @pytest.mark.asyncio
    async def test_backfill_no_duplicates(self, db: AsyncSession):
        """Overlapping backfill does not create duplicate events."""
        events = [
            {
                "transaction_hash": "0x" + "aa" * 32,
                "log_index": 0,
                "block_number": 100,
                "block_hash": "0x" + "bb" * 32,
                "event_name": "JobCreated",
                "event_data": {},
            },
            {
                "transaction_hash": "0x" + "cc" * 32,
                "log_index": 0,
                "block_number": 101,
                "block_hash": "0x" + "dd" * 32,
                "event_name": "ProviderAssigned",
                "event_data": {},
            },
        ]
        recorded1 = await backfill_events(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            events=events,
            from_block=90,
            to_block=110,
        )
        assert len(recorded1) == 2

        # Overlapping backfill
        recorded2 = await backfill_events(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            events=events,
            from_block=95,
            to_block=115,
        )
        assert len(recorded2) == 2  # Returns existing events
        assert recorded2[0].id == recorded1[0].id  # Same IDs

    @pytest.mark.asyncio
    async def test_confirmation_progression(self, db: AsyncSession):
        """Events progress: pending → confirmed → finalized."""
        ev = await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=100,
            block_hash="0x" + "ef" * 32,
            event_name="JobCreated",
            event_data={},
        )
        assert ev.confirmation_status == "pending"

        confirmed = await confirm_event(db, ev.id)
        assert confirmed.confirmation_status == "confirmed"

        finalized = await finalize_event(db, ev.id)
        assert finalized.confirmation_status == "finalized"

    @pytest.mark.asyncio
    async def test_batch_confirmation_at_block(self, db: AsyncSession):
        """confirm_events_at_block confirms enough pending events."""
        for i in range(3):
            await record_event(
                db,
                chain_id=421614,
                contract_address="0x" + "ab" * 20,
                transaction_hash=f"0x{i:064x}",
                log_index=0,
                block_number=100 + i,
                block_hash="0x" + "ef" * 32,
                event_name="JobCreated",
                event_data={},
            )

        # Block 102 with 2 confirmations required: block 100 has 2 confirmations
        count = await confirm_events_at_block(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            current_block=102,
            confirmations_required=2,
        )
        assert count >= 1

    @pytest.mark.asyncio
    async def test_reorg_removes_non_finalized(self, db: AsyncSession):
        """Reorg demotes non-finalized events with changed block hash."""
        ev = await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=100,
            block_hash="0x" + "old" * 32,
            event_name="JobCreated",
            event_data={},
        )
        await confirm_event(db, ev.id)

        result = await handle_reorg(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            reverted_block_number=100,
            reverted_block_hash="0x" + "new" * 32,
        )
        assert result["orphaned_events_count"] >= 1

        # Event should be demoted to pending
        from sqlalchemy import select

        r = await db.execute(select(BlockchainEvent).where(BlockchainEvent.id == ev.id))
        updated = r.scalar_one()
        assert updated.confirmation_status == "pending"

    @pytest.mark.asyncio
    async def test_reorg_preserves_finalized(self, db: AsyncSession):
        """Finalized events are NOT deleted during reorg."""
        ev = await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "ff" * 32,
            log_index=0,
            block_number=100,
            block_hash="0x" + "old" * 32,
            event_name="JobSettled",
            event_data={},
        )
        await finalize_event(db, ev.id)

        await handle_reorg(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            reverted_block_number=100,
            reverted_block_hash="0x" + "new" * 32,
        )

        from sqlalchemy import select

        r = await db.execute(select(BlockchainEvent).where(BlockchainEvent.id == ev.id))
        updated = r.scalar_one()
        assert updated.confirmation_status == "finalized"  # NOT deleted

    @pytest.mark.asyncio
    async def test_replace_non_finalized_event(self, db: AsyncSession):
        """Non-finalized event can be replaced with updated data."""
        await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=100,
            block_hash="0x" + "old" * 32,
            event_name="JobCreated",
            event_data={"old": True},
        )

        replaced = await replace_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            old_tx_hash="0x" + "cd" * 32,
            old_log_index=0,
            new_event_data={"block_number": 200, "block_hash": "0x" + "new" * 32, "event_data": {"new": True}},
        )
        assert replaced is not None
        assert replaced.block_number == 200
        assert replaced.confirmation_status == "pending"  # Reset for re-confirmation

    @pytest.mark.asyncio
    async def test_replace_finalized_event_not_modified(self, db: AsyncSession):
        """Finalized event replacement returns existing event unchanged."""
        ev = await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=100,
            block_hash="0x" + "ef" * 32,
            event_name="JobCreated",
            event_data={},
        )
        await finalize_event(db, ev.id)

        replaced = await replace_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            old_tx_hash="0x" + "cd" * 32,
            old_log_index=0,
            new_event_data={"block_number": 200},
        )
        assert replaced.id == ev.id
        assert replaced.confirmation_status == "finalized"  # Unchanged

    @pytest.mark.asyncio
    async def test_db_failure_recovery(self, db: AsyncSession):
        """recover_from_db_failure returns existing events for block range."""
        await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=100,
            block_hash="0x" + "ef" * 32,
            event_name="JobCreated",
            event_data={},
        )

        recovery = await recover_from_db_failure(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            from_block=90,
            to_block=110,
        )
        assert recovery["existing_events_count"] == 1
        assert recovery["can_process_missing"] is True

    @pytest.mark.asyncio
    async def test_reconciliation_idempotent(self, db: AsyncSession, seed_model, seed_user):
        """Running reconciliation twice gives same result."""
        from app.services.job_service import create_job

        job = await create_job(
            db,
            user_id=seed_user.id,
            model_id="resnet50",
            chain_job_id="0x" + uuid.uuid4().hex,
            price_base_units=500000000000000000,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        r1 = await reconcile_job_state(db, job.id)
        r2 = await reconcile_job_state(db, job.id)
        assert r1 == r2

    @pytest.mark.asyncio
    async def test_unconfirmed_events_query(self, db: AsyncSession):
        """get_unconfirmed_events returns only pending events."""
        await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=100,
            block_hash="0x" + "ef" * 32,
            event_name="JobCreated",
            event_data={},
        )

        events = await get_unconfirmed_events(db, chain_id=421614)
        assert len(events) == 1
        assert events[0].confirmation_status == "pending"

        # Confirm it
        await confirm_event(db, events[0].id)

        events2 = await get_unconfirmed_events(db, chain_id=421614)
        assert len(events2) == 0
