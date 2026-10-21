"""Tests for the job service (PRD v3.1 §10, §16)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SupportedModel, User
from app.services.job_service import (
    confirm_job_escrow,
    create_job,
    get_job,
    list_user_jobs,
    update_job_status,
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
        wallet_address="0x1234567890abcdef1234567890abcdef12345678",
        role="user",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_create_job(db: AsyncSession, seed_model, seed_user):
    job = await create_job(
        db,
        user_id=seed_user.id,
        model_id="resnet50",
        chain_job_id="0x550e8400e29b41d4a716446655440000",
        price_base_units=500000000000000000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert job is not None
    assert job.user_id == seed_user.id
    assert job.model_id == "resnet50"
    assert job.status == "pending_blockchain"
    assert job.chain_job_id == "0x550e8400e29b41d4a716446655440000"


@pytest.mark.asyncio
async def test_create_job_default_status(db: AsyncSession, seed_model, seed_user):
    job = await create_job(
        db,
        user_id=seed_user.id,
        model_id="resnet50",
        chain_job_id="0x550e8400e29b41d4a716446655440000",
        price_base_units=500000000000000000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert job.status == "pending_blockchain"
    assert job.max_attempts == 3
    assert job.current_attempt == 0


@pytest.mark.asyncio
async def test_confirm_job_escrow(db: AsyncSession, seed_model, seed_user):
    job = await create_job(
        db,
        user_id=seed_user.id,
        model_id="resnet50",
        chain_job_id="0x550e8400e29b41d4a716446655440000",
        price_base_units=500000000000000000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    await db.commit()

    confirmed = await confirm_job_escrow(
        db,
        job_id=job.id,
        tx_hash="0xabc123",
        escrow_amount=500000000000000000,
    )
    assert confirmed.status == "queued"
    assert confirmed.blockchain_tx_hash == "0xabc123"
    assert confirmed.blockchain_escrow_amount == 500000000000000000


@pytest.mark.asyncio
async def test_get_job(db: AsyncSession, seed_model, seed_user):
    job = await create_job(
        db,
        user_id=seed_user.id,
        model_id="resnet50",
        chain_job_id="0x550e8400e29b41d4a716446655440000",
        price_base_units=500000000000000000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    await db.commit()

    fetched = await get_job(db, job.id)
    assert fetched is not None
    assert fetched.id == job.id


@pytest.mark.asyncio
async def test_get_job_not_found(db: AsyncSession):
    result = await get_job(db, uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_list_user_jobs(db: AsyncSession, seed_model, seed_user):
    for i in range(3):
        await create_job(
            db,
            user_id=seed_user.id,
            model_id="resnet50",
            chain_job_id=f"0x{i:064d}",
            price_base_units=500000000000000000,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    await db.commit()

    jobs = await list_user_jobs(db, seed_user.id)
    assert len(jobs) == 3


@pytest.mark.asyncio
async def test_list_user_jobs_empty(db: AsyncSession, seed_user):
    jobs = await list_user_jobs(db, seed_user.id)
    assert len(jobs) == 0


@pytest.mark.asyncio
async def test_update_job_status(db: AsyncSession, seed_model, seed_user):
    job = await create_job(
        db,
        user_id=seed_user.id,
        model_id="resnet50",
        chain_job_id="0x550e8400e29b41d4a716446655440000",
        price_base_units=500000000000000000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    await db.commit()

    updated = await update_job_status(db, job.id, "queued")
    assert updated.status == "queued"


@pytest.mark.asyncio
async def test_confirm_escrow_wrong_status(db: AsyncSession, seed_model, seed_user):
    job = await create_job(
        db,
        user_id=seed_user.id,
        model_id="resnet50",
        chain_job_id="0x550e8400e29b41d4a716446655440000",
        price_base_units=500000000000000000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    # First confirm to move to queued
    await confirm_job_escrow(db, job_id=job.id, tx_hash="0xfirst", escrow_amount=500000000000000000)
    await db.commit()

    with pytest.raises(ValueError, match="expected pending_blockchain"):
        await confirm_job_escrow(
            db,
            job_id=job.id,
            tx_hash="0xabc123",
            escrow_amount=500000000000000000,
        )
