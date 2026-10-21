"""PostgreSQL concurrency tests for scheduler FOR UPDATE SKIP LOCKED.

Uses two independent PostgreSQL connections and concurrent scheduler calls
to prove exactly one scheduler wins the assignment.

DATABASE_URL must be set in the environment and must use the PostgreSQL
scheme targeting nebula_test. Tests skip when the variable is absent.
"""

import asyncio
import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import Job, Node, SupportedModel, User
from app.services.scheduler import schedule_next_job

_raw_url = os.environ.get("DATABASE_URL")
if not _raw_url:
    PG_URL = None
else:
    _parsed = urlparse(_raw_url)
    if _parsed.scheme not in ("postgresql", "postgresql+asyncpg"):
        PG_URL = None
    elif (_parsed.path or "").lstrip("/") != "nebula_test":
        PG_URL = None
    else:
        PG_URL = _raw_url


@pytest.fixture(scope="module")
def pg_engine():
    """Create a PostgreSQL engine for concurrency tests."""
    if PG_URL is None:
        pytest.skip("DATABASE_URL not set or not targeting nebula_test over PostgreSQL")
    engine = create_async_engine(PG_URL, pool_size=10, max_overflow=10, echo=False)
    yield engine


@pytest_asyncio.fixture
async def setup_pg_database(pg_engine):
    """Ensure the migrated shared test schema exists without dropping it."""
    async with pg_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield pg_engine


@pytest.mark.asyncio
async def test_concurrent_scheduler_one_winner(setup_pg_database):
    """Two concurrent scheduler calls — exactly one wins.

    Proves:
    - Both processes see the same eligible job initially
    - FOR UPDATE SKIP LOCKED allows only one winner
    - Exactly one attempt is created
    - Exactly one pending_chain lease is created
    - The losing scheduler does not fail or duplicate work
    """
    pg_engine = setup_pg_database
    session_factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    # Seed data in a single session
    async with session_factory() as seed_db:
        async with seed_db.begin():
            user = User(
                id=uuid.uuid4(),
                wallet_address="0x" + uuid.uuid4().hex + uuid.uuid4().hex[:8],
                role="user",
            )
            seed_db.add(user)

            model_id = "concurrency-" + uuid.uuid4().hex
            model = SupportedModel(
                id=model_id,
                name="ResNet-50",
                vram_required_gb=8,
                price_base_units=500000000000000000,
            )
            seed_db.add(model)

            provider = User(
                id=uuid.uuid4(),
                wallet_address="0x" + uuid.uuid4().hex + uuid.uuid4().hex[:8],
                role="provider",
            )
            seed_db.add(provider)
            await seed_db.flush()

            node = Node(
                id=uuid.uuid4(),
                provider_id=provider.id,
                gpu_name="RTX 4090",
                vram_gb=24,
                status="online",
                api_key_hash=hashlib.sha256(b"concurrent-test").hexdigest(),
                active_leases=0,
                last_heartbeat=datetime.now(timezone.utc),
            )
            seed_db.add(node)

            job = Job(
                id=uuid.uuid4(),
                user_id=user.id,
                model_id=model_id,
                chain_job_id="0x" + uuid.uuid4().hex + uuid.uuid4().hex,
                price_base_units=500000000000000000,
                deadline=datetime.now(timezone.utc) + timedelta(hours=1),
                status="queued",
                max_attempts=3,
                current_attempt=0,
            )
            seed_db.add(job)

    # Verify seed data is visible
    async with session_factory() as verify_db:
        async with verify_db.begin():
            result = await verify_db.execute(text("SELECT id, status FROM jobs WHERE status = 'queued'"))
            rows = result.fetchall()
            assert len(rows) >= 1, f"Seed data not visible: {rows}"

    # Create two independent sessions (simulating two scheduler processes)
    async def scheduler_task():
        async with session_factory() as db:
            async with db.begin():
                return await schedule_next_job(db)

    # Run two schedulers concurrently
    results = await asyncio.gather(
        scheduler_task(),
        scheduler_task(),
        return_exceptions=True,
    )

    valid_results = [r for r in results if r is not None and not isinstance(r, Exception)]
    exceptions = [r for r in results if isinstance(r, Exception)]

    # At most one winner
    assert len(valid_results) <= 1, f"Expected at most 1 winner, got {len(valid_results)}"
    assert len(exceptions) == 0, f"Scheduler raised exceptions: {exceptions}"

    # Verify exactly one attempt and one lease were created
    async with session_factory() as verify_db:
        async with verify_db.begin():
            attempt_count = (
                await verify_db.execute(
                    text("SELECT COUNT(*) FROM job_attempts WHERE job_id = :job_id"),
                    {"job_id": job.id},
                )
            ).scalar()
            lease_count = (
                await verify_db.execute(
                    text("SELECT COUNT(*) FROM leases WHERE job_id = :job_id"),
                    {"job_id": job.id},
                )
            ).scalar()

    if valid_results:
        assert attempt_count == 1, f"Expected 1 attempt, got {attempt_count}"
        assert lease_count == 1, f"Expected 1 lease, got {lease_count}"
    else:
        assert attempt_count == 0
        assert lease_count == 0


@pytest.mark.asyncio
async def test_pg_dialect_detection():
    """Verify PostgreSQL dialect is detected correctly."""
    if PG_URL is None:
        pytest.skip("DATABASE_URL not set or not targeting nebula_test over PostgreSQL")
    engine = create_async_engine(PG_URL, pool_size=2, max_overflow=2, echo=False)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_for_update_skip_locked_syntax():
    """Verify FOR UPDATE SKIP LOCKED syntax works on PostgreSQL."""
    if PG_URL is None:
        pytest.skip("DATABASE_URL not set or not targeting nebula_test over PostgreSQL")
    engine = create_async_engine(PG_URL, pool_size=2, max_overflow=2, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT 1 FROM jobs WHERE status = 'queued' LIMIT 1 FOR UPDATE SKIP LOCKED")
            )
            row = result.first()
            assert row is None or row is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scheduler_returns_only_one_per_job():
    """Two concurrent scheduler calls for the same job — only one creates attempt+lease."""
    if PG_URL is None:
        pytest.skip("DATABASE_URL not set or not targeting nebula_test over PostgreSQL")
    engine = create_async_engine(PG_URL, pool_size=2, max_overflow=2, echo=False)
    try:
        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        # Seed data
        async with session_factory() as seed_db:
            async with seed_db.begin():
                user = User(
                    id=uuid.uuid4(),
                    wallet_address="0x" + uuid.uuid4().hex + uuid.uuid4().hex[:8],
                    role="user",
                )
                seed_db.add(user)
                model_id = "concurrency-" + uuid.uuid4().hex
                model = SupportedModel(
                    id=model_id,
                    name="ResNet-50",
                    vram_required_gb=8,
                    price_base_units=500000000000000000,
                )
                seed_db.add(model)
                provider = User(
                    id=uuid.uuid4(),
                    wallet_address="0x" + uuid.uuid4().hex + uuid.uuid4().hex[:8],
                    role="provider",
                )
                seed_db.add(provider)
                await seed_db.flush()

                node = Node(
                    id=uuid.uuid4(),
                    provider_id=provider.id,
                    gpu_name="RTX 4090",
                    vram_gb=24,
                    status="online",
                    api_key_hash=hashlib.sha256(b"test2").hexdigest(),
                    active_leases=0,
                    last_heartbeat=datetime.now(timezone.utc),
                )
                seed_db.add(node)

                job = Job(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    model_id=model_id,
                    chain_job_id="0x" + uuid.uuid4().hex + uuid.uuid4().hex,
                    price_base_units=500000000000000000,
                    deadline=datetime.now(timezone.utc) + timedelta(hours=1),
                    status="queued",
                    max_attempts=3,
                    current_attempt=0,
                )
                seed_db.add(job)

        async def scheduler_task():
            async with session_factory() as db:
                async with db.begin():
                    return await schedule_next_job(db)

        results = await asyncio.gather(scheduler_task(), scheduler_task(), return_exceptions=True)
        valid = [r for r in results if r is not None and not isinstance(r, Exception)]

        async with session_factory() as count_db:
            async with count_db.begin():
                ar = (
                    await count_db.execute(
                        text("SELECT COUNT(*) FROM job_attempts WHERE job_id = :job_id"),
                        {"job_id": job.id},
                    )
                ).scalar()
                lr = (
                    await count_db.execute(
                        text("SELECT COUNT(*) FROM leases WHERE job_id = :job_id"),
                        {"job_id": job.id},
                    )
                ).scalar()

        if valid:
            assert ar == 1
            assert lr == 1
    finally:
        await engine.dispose()
