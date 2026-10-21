"""Tests for blockchain event ingestion and reconciliation (PRD §19, §20)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SupportedModel, User
from app.services.blockchain_events import (
    confirm_event,
    get_unconfirmed_events,
    reconcile_job_state,
    record_event,
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
    user = User(
        id=uuid.uuid4(),
        wallet_address="0x" + uuid.uuid4().hex,
        role="user",
    )
    db.add(user)
    await db.flush()
    return user


class TestBlockchainEvents:
    @pytest.mark.asyncio
    async def test_record_event(self, db: AsyncSession):
        event = await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=12345,
            block_hash="0x" + "ef" * 32,
            event_name="JobCreated",
            event_data={"jobId": "0x" + "01" * 32, "user": "0x" + "02" * 20},
        )
        assert event is not None
        assert event.event_name == "JobCreated"
        assert event.confirmation_status == "pending"

    @pytest.mark.asyncio
    async def test_record_event_duplicate_returns_existing(self, db: AsyncSession):
        event1 = await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=12345,
            block_hash="0x" + "ef" * 32,
            event_name="JobCreated",
            event_data={},
        )
        await db.flush()

        # Same event again should return existing (idempotent)
        event2 = await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=12345,
            block_hash="0x" + "ef" * 32,
            event_name="JobCreated",
            event_data={},
        )
        assert event2.id == event1.id  # Same event returned

    @pytest.mark.asyncio
    async def test_get_unconfirmed_events(self, db: AsyncSession):
        await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=12345,
            block_hash="0x" + "ef" * 32,
            event_name="JobCreated",
            event_data={},
        )
        await db.flush()

        events = await get_unconfirmed_events(db, chain_id=421614)
        assert len(events) == 1
        assert events[0].confirmation_status == "pending"

    @pytest.mark.asyncio
    async def test_confirm_event(self, db: AsyncSession):
        event = await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=12345,
            block_hash="0x" + "ef" * 32,
            event_name="JobCreated",
            event_data={},
        )
        await db.flush()

        confirmed = await confirm_event(db, event.id)
        assert confirmed.confirmation_status == "confirmed"

    @pytest.mark.asyncio
    async def test_reconcile_job_state_match(self, db: AsyncSession, seed_model, seed_user):
        from app.services.job_service import create_job

        job = await create_job(
            db,
            user_id=seed_user.id,
            model_id="resnet50",
            chain_job_id="0x" + uuid.uuid4().hex,
            price_base_units=500000000000000000,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        await db.flush()

        # Record a matching event
        event = await record_event(
            db,
            chain_id=421614,
            contract_address="0x" + "ab" * 20,
            transaction_hash="0x" + "cd" * 32,
            log_index=0,
            block_number=12345,
            block_hash="0x" + "ef" * 32,
            event_name="JobCreated",
            event_data={"chainJobId": job.chain_job_id},
            job_id=job.id,
        )
        await confirm_event(db, event.id)
        await db.flush()

        result = await reconcile_job_state(db, job.id)
        assert result["status"] == "match"
        assert result["db_status"] == job.status

    @pytest.mark.asyncio
    async def test_reconcile_job_no_events(self, db: AsyncSession, seed_model, seed_user):
        from app.services.job_service import create_job

        job = await create_job(
            db,
            user_id=seed_user.id,
            model_id="resnet50",
            chain_job_id="0x" + uuid.uuid4().hex,
            price_base_units=500000000000000000,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        await db.flush()

        result = await reconcile_job_state(db, job.id)
        assert result["status"] == "no_chain_events"
