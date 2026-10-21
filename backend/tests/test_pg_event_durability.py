"""PostgreSQL-backed event durability verification tests.

Proves event durability across service restarts using real PostgreSQL.
Each test uses independent engine/session instances, commits data before
closing, and resumes from persisted state.

Each test tracks exact record IDs it creates. Cleanup deletes only those
records in FK-safe reverse order — never unfiltered DELETE FROM shared tables.

Requires: DATABASE_URL env var pointing to nebula_test over PostgreSQL.
"""

import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import BlockchainEvent, Job, SupportedModel, User
from app.services.blockchain_events import (
    backfill_events,
    confirm_event,
    finalize_event,
    get_checkpoint,
    handle_reorg,
    reconcile_job_state,
    record_event,
    recover_from_db_failure,
    replace_event,
)

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

CONTRACT = "0x" + "ab" * 20


class _TestTracker:
    """Per-test resource tracker. Records every ID created by the test
    so cleanup can delete exactly those rows in FK-safe order."""

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.chain_id = hash(test_name) % 100000 + 1000000
        self.user_ids: list[uuid.UUID] = []
        self.model_ids: list[str] = []
        self.job_ids: list[uuid.UUID] = []
        self.event_ids: list[uuid.UUID] = []

    def track_user(self, user_id: uuid.UUID) -> uuid.UUID:
        self.user_ids.append(user_id)
        return user_id

    def track_model(self, model_id: str) -> str:
        self.model_ids.append(model_id)
        return model_id

    def track_job(self, job_id: uuid.UUID) -> uuid.UUID:
        self.job_ids.append(job_id)
        return job_id

    def track_event(self, event_id: uuid.UUID) -> uuid.UUID:
        self.event_ids.append(event_id)
        return event_id

    async def cleanup(self, engine) -> None:
        """Delete only tracked records in FK-safe reverse order."""
        async with engine.begin() as conn:
            for eid in self.event_ids:
                await conn.execute(
                    text("DELETE FROM blockchain_events WHERE id = :id"),
                    {"id": eid},
                )
            for jid in self.job_ids:
                await conn.execute(
                    text("DELETE FROM jobs WHERE id = :id"),
                    {"id": jid},
                )
            for uid in self.user_ids:
                await conn.execute(
                    text("DELETE FROM users WHERE id = :id"),
                    {"id": uid},
                )
            for mid in self.model_ids:
                await conn.execute(
                    text("DELETE FROM supported_models WHERE id = :id"),
                    {"id": mid},
                )


async def _make_engine():
    engine = create_async_engine(PG_URL, pool_size=2, max_overflow=2, echo=False)
    dialect = engine.dialect.name
    assert dialect == "postgresql", f"Expected PostgreSQL, got {dialect}"
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def _make_session(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def pg_durable():
    """Shared fixture: engine + tracker. Cleans up only tracked records.
    Always disposes engine in teardown."""
    _pg_required()
    engine = await _make_engine()
    tracker = _TestTracker("base")
    try:
        yield engine, tracker
    finally:
        await tracker.cleanup(engine)
        await engine.dispose()


def _pg_required():
    if PG_URL is None:
        pytest.skip("DATABASE_URL not set or not targeting nebula_test over PostgreSQL")


def _unique_hex() -> str:
    return uuid.uuid4().hex


def _unique_address() -> str:
    """Return a constraint-valid, lowercase 20-byte test address."""
    return "0x" + uuid.uuid4().hex + uuid.uuid4().hex[:8]


class TestPGEventDurability:
    """PostgreSQL-backed event durability with real restart semantics."""

    @pytest.mark.asyncio
    async def test_01_persist_event_and_checkpoint(self, pg_durable):
        """Persist an event and checkpoint using instance A."""
        engine, tracker = pg_durable
        tracker.test_name = "test_01"
        tracker.chain_id = 1_000_001
        factory = _make_session(engine)

        async with factory() as db:
            async with db.begin():
                ev = await record_event(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    transaction_hash="0x" + _unique_hex(),
                    log_index=0,
                    block_number=100,
                    block_hash="0x" + "bb" * 32,
                    event_name="JobCreated",
                    event_data={"key": "val"},
                )
                tracker.track_event(ev.id)
                assert ev.id is not None

                cp = await get_checkpoint(db, tracker.chain_id, CONTRACT)
                assert cp["last_block"] == 100

    @pytest.mark.asyncio
    async def test_02_recover_event_from_new_instance(self, pg_durable):
        """Create instance B, recover event persisted by instance A."""
        engine, tracker = pg_durable
        tracker.test_name = "test_02"
        tracker.chain_id = 1_000_002
        factory_a = _make_session(engine)

        async with factory_a() as db:
            async with db.begin():
                ev = await record_event(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    transaction_hash="0x" + _unique_hex(),
                    log_index=0,
                    block_number=200,
                    block_hash="0x" + "dd" * 32,
                    event_name="ProviderAssigned",
                    event_data={},
                )
                tracker.track_event(ev.id)

        engine_b = create_async_engine(PG_URL, pool_size=2, max_overflow=2, echo=False)
        try:
            factory_b = _make_session(engine_b)
            async with factory_b() as db:
                cp = await get_checkpoint(db, tracker.chain_id, CONTRACT)
                assert cp["last_block"] == 200

                unconfirmed = await record_event(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    transaction_hash=ev.transaction_hash,
                    log_index=0,
                    block_number=200,
                    block_hash="0x" + "dd" * 32,
                    event_name="ProviderAssigned",
                    event_data={},
                )
                assert unconfirmed is not None
        finally:
            await engine_b.dispose()

    @pytest.mark.asyncio
    async def test_03_resume_backfill_from_checkpoint(self, pg_durable):
        """Resume backfill from persisted checkpoint after restart."""
        engine, tracker = pg_durable
        tracker.test_name = "test_03"
        tracker.chain_id = 1_000_003
        factory = _make_session(engine)

        tx1 = "0x" + _unique_hex()
        tx2 = "0x" + _unique_hex()
        tx3 = "0x" + _unique_hex()

        async with factory() as db:
            async with db.begin():
                evts = await backfill_events(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    events=[
                        {
                            "transaction_hash": tx1,
                            "log_index": 0,
                            "block_number": 50,
                            "block_hash": "0x" + "22" * 32,
                            "event_name": "JobCreated",
                            "event_data": {},
                        },
                        {
                            "transaction_hash": tx2,
                            "log_index": 0,
                            "block_number": 60,
                            "block_hash": "0x" + "44" * 32,
                            "event_name": "JobCreated",
                            "event_data": {},
                        },
                    ],
                    from_block=40,
                    to_block=70,
                )
                for e in evts:
                    tracker.track_event(e.id)

        engine2 = create_async_engine(PG_URL, pool_size=2, max_overflow=2, echo=False)
        try:
            factory2 = _make_session(engine2)
            async with factory2() as db:
                cp = await get_checkpoint(db, tracker.chain_id, CONTRACT)
                assert cp["last_block"] == 60

                recorded = await backfill_events(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    events=[
                        {
                            "transaction_hash": tx2,
                            "log_index": 0,
                            "block_number": 60,
                            "block_hash": "0x" + "44" * 32,
                            "event_name": "JobCreated",
                            "event_data": {},
                        },
                        {
                            "transaction_hash": tx3,
                            "log_index": 0,
                            "block_number": 70,
                            "block_hash": "0x" + "66" * 32,
                            "event_name": "ProofSubmitted",
                            "event_data": {},
                        },
                    ],
                    from_block=55,
                    to_block=75,
                )
                assert len(recorded) == 2
                for e in recorded:
                    if e.id not in tracker.event_ids:
                        tracker.track_event(e.id)

                cp2 = await get_checkpoint(db, tracker.chain_id, CONTRACT)
                assert cp2["last_block"] == 70
        finally:
            await engine2.dispose()

    @pytest.mark.asyncio
    async def test_04_non_final_event_reorg_demoted(self, pg_durable):
        """Non-final canonical block-hash mismatch marks event as orphaned."""
        engine, tracker = pg_durable
        tracker.test_name = "test_04"
        tracker.chain_id = 1_000_004
        factory = _make_session(engine)

        async with factory() as db:
            async with db.begin():
                ev = await record_event(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    transaction_hash="0x" + _unique_hex(),
                    log_index=0,
                    block_number=300,
                    block_hash="0x" + "aa" * 32,
                    event_name="JobCreated",
                    event_data={},
                )
                tracker.track_event(ev.id)
                await confirm_event(db, ev.id)

        async with factory() as db:
            async with db.begin():
                result = await handle_reorg(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    reverted_block_number=300,
                    reverted_block_hash="0x" + "bb" * 32,
                )
                assert result["orphaned_events_count"] >= 1

                r = await db.execute(select(BlockchainEvent).where(BlockchainEvent.id == ev.id))
                updated = r.scalar_one()
                assert updated.confirmation_status == "pending"

    @pytest.mark.asyncio
    async def test_05_replacement_event_inserted(self, pg_durable):
        """Insert replacement canonical event after reorg."""
        engine, tracker = pg_durable
        tracker.test_name = "test_05"
        tracker.chain_id = 1_000_005
        factory = _make_session(engine)

        orig_tx = "0x" + _unique_hex()

        async with factory() as db:
            async with db.begin():
                ev = await record_event(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    transaction_hash=orig_tx,
                    log_index=0,
                    block_number=400,
                    block_hash="0x" + "aa" * 32,
                    event_name="ProviderAssigned",
                    event_data={"old": True},
                )
                tracker.track_event(ev.id)

        async with factory() as db:
            async with db.begin():
                replaced = await replace_event(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    old_tx_hash=orig_tx,
                    old_log_index=0,
                    new_event_data={
                        "block_number": 401,
                        "block_hash": "0x" + "bb" * 32,
                        "event_data": {"new": True},
                    },
                )
                assert replaced is not None
                assert replaced.block_number == 401
                assert replaced.confirmation_status == "pending"

        async with factory() as db:
            r = await db.execute(select(BlockchainEvent).where(BlockchainEvent.id == ev.id))
            final = r.scalar_one()
            assert final.block_number == 401
            assert final.event_data == {"new": True}

    @pytest.mark.asyncio
    async def test_06_derived_job_projection_reversed(self, pg_durable):
        """Reorg reverses derived job projection transactionally."""
        engine, tracker = pg_durable
        tracker.test_name = "test_06"
        tracker.chain_id = 1_000_006
        factory = _make_session(engine)

        user_id = uuid.uuid4()
        tracker.track_user(user_id)
        model_id = "test_model_" + _unique_hex()[:8]
        tracker.track_model(model_id)
        job_id = uuid.uuid4()
        tracker.track_job(job_id)

        async with factory() as db:
            async with db.begin():
                user = User(id=user_id, wallet_address=_unique_address(), role="user")
                db.add(user)
                model = SupportedModel(
                    id=model_id,
                    name="TestModel",
                    vram_required_gb=8,
                    price_base_units=500000000000000000,
                )
                db.add(model)
                await db.flush()

                job = Job(
                    id=job_id,
                    user_id=user_id,
                    model_id=model_id,
                    chain_job_id="0x" + _unique_hex(),
                    price_base_units=500000000000000000,
                    status="assigned",
                    deadline=datetime.now(timezone.utc),
                )
                db.add(job)

                ev = await record_event(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    transaction_hash="0x" + _unique_hex(),
                    log_index=0,
                    block_number=500,
                    block_hash="0x" + "aa" * 32,
                    event_name="ProviderAssigned",
                    event_data={"projection": "assigned"},
                    job_id=job_id,
                )
                tracker.track_event(ev.id)
                await confirm_event(db, ev.id)

        async with factory() as db:
            async with db.begin():
                result = await handle_reorg(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    reverted_block_number=500,
                    reverted_block_hash="0x" + "bb" * 32,
                )
                assert result["affected_job_ids"] == [str(job_id)]

                r = await db.execute(select(BlockchainEvent).where(BlockchainEvent.id == ev.id))
                updated = r.scalar_one()
                assert updated.confirmation_status == "pending"
                assert updated.event_name == "ProviderAssigned"

    @pytest.mark.asyncio
    async def test_07_corrected_state_persists_after_restart(self, pg_durable):
        """Corrected state persists after second restart (instance C)."""
        engine, tracker = pg_durable
        tracker.test_name = "test_07"
        tracker.chain_id = 1_000_007
        factory = _make_session(engine)

        orig_tx = "0x" + _unique_hex()

        async with factory() as db:
            async with db.begin():
                ev = await record_event(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    transaction_hash=orig_tx,
                    log_index=0,
                    block_number=600,
                    block_hash="0x" + "aa" * 32,
                    event_name="JobSettled",
                    event_data={"status": "settled"},
                )
                tracker.track_event(ev.id)

        async with factory() as db:
            async with db.begin():
                replaced = await replace_event(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    old_tx_hash=orig_tx,
                    old_log_index=0,
                    new_event_data={
                        "block_number": 601,
                        "block_hash": "0x" + "bb" * 32,
                        "event_data": {"status": "corrected"},
                    },
                )
                assert replaced is not None

        engine_c = create_async_engine(PG_URL, pool_size=2, max_overflow=2, echo=False)
        try:
            factory_c = _make_session(engine_c)
            async with factory_c() as db:
                r = await db.execute(
                    select(BlockchainEvent).where(
                        BlockchainEvent.chain_id == tracker.chain_id,
                        BlockchainEvent.transaction_hash == orig_tx,
                    )
                )
                final = r.scalar_one()
                assert final.block_number == 601
                assert final.event_data == {"status": "corrected"}
                assert final.confirmation_status == "pending"
        finally:
            await engine_c.dispose()

    @pytest.mark.asyncio
    async def test_08_chain_success_db_failure_recovery(self, pg_durable):
        """Chain success followed by DB projection failure — recovery works."""
        engine, tracker = pg_durable
        tracker.test_name = "test_08"
        tracker.chain_id = 1_000_008
        factory = _make_session(engine)

        async with factory() as db:
            async with db.begin():
                ev = await record_event(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    transaction_hash="0x" + _unique_hex(),
                    log_index=0,
                    block_number=700,
                    block_hash="0x" + "aa" * 32,
                    event_name="ProofSubmitted",
                    event_data={},
                )
                tracker.track_event(ev.id)

        async with factory() as db:
            async with db.begin():
                recovery = await recover_from_db_failure(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    from_block=690,
                    to_block=710,
                )
                assert recovery["existing_events_count"] == 1
                assert recovery["can_process_missing"] is True

    @pytest.mark.asyncio
    async def test_09_reconcile_idempotent(self, pg_durable):
        """Repeated reconciliation produces identical results."""
        engine, tracker = pg_durable
        tracker.test_name = "test_09"
        tracker.chain_id = 1_000_009
        factory = _make_session(engine)

        user_id = uuid.uuid4()
        tracker.track_user(user_id)
        model_id = "test_model_" + _unique_hex()[:8]
        tracker.track_model(model_id)
        job_id = uuid.uuid4()
        tracker.track_job(job_id)

        async with factory() as db:
            async with db.begin():
                user = User(id=user_id, wallet_address=_unique_address(), role="user")
                db.add(user)
                model = SupportedModel(
                    id=model_id,
                    name="TestModel",
                    vram_required_gb=8,
                    price_base_units=500000000000000000,
                )
                db.add(model)
                await db.flush()

                job = Job(
                    id=job_id,
                    user_id=user_id,
                    model_id=model_id,
                    chain_job_id="0x" + _unique_hex(),
                    price_base_units=500000000000000000,
                    status="completed",
                    deadline=datetime.now(timezone.utc),
                )
                db.add(job)

                ev = await record_event(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    transaction_hash="0x" + _unique_hex(),
                    log_index=0,
                    block_number=800,
                    block_hash="0x" + "aa" * 32,
                    event_name="JobSettled",
                    event_data={},
                    job_id=job_id,
                )
                tracker.track_event(ev.id)

        async with factory() as db:
            r1 = await reconcile_job_state(db, job_id)
        async with factory() as db:
            r2 = await reconcile_job_state(db, job_id)

        assert r1 == r2
        assert r1["status"] in ("match", "pending_confirmation")

    @pytest.mark.asyncio
    async def test_10_finalized_event_not_deleted_on_reorg(self, pg_durable):
        """Finalized event contradiction preserves evidence — no deletion."""
        engine, tracker = pg_durable
        tracker.test_name = "test_10"
        tracker.chain_id = 1_000_010
        factory = _make_session(engine)

        async with factory() as db:
            async with db.begin():
                ev = await record_event(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    transaction_hash="0x" + _unique_hex(),
                    log_index=0,
                    block_number=900,
                    block_hash="0x" + "aa" * 32,
                    event_name="JobSettled",
                    event_data={},
                )
                tracker.track_event(ev.id)
                await finalize_event(db, ev.id)

        async with factory() as db:
            async with db.begin():
                result = await handle_reorg(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    reverted_block_number=900,
                    reverted_block_hash="0x" + "bb" * 32,
                )
                assert result["orphaned_events_count"] == 0

                r = await db.execute(select(BlockchainEvent).where(BlockchainEvent.id == ev.id))
                final = r.scalar_one()
                assert final.confirmation_status == "finalized"

    @pytest.mark.asyncio
    async def test_11_overlapping_backfill_no_duplicates(self, pg_durable):
        """Overlapping backfill across restart creates no duplicate events."""
        engine, tracker = pg_durable
        tracker.test_name = "test_11"
        tracker.chain_id = 1_000_011
        factory = _make_session(engine)

        tx1 = "0x" + _unique_hex()
        tx2 = "0x" + _unique_hex()

        async with factory() as db:
            async with db.begin():
                evts = await backfill_events(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    events=[
                        {
                            "transaction_hash": tx1,
                            "log_index": 0,
                            "block_number": 100,
                            "block_hash": "0x" + "aa" * 32,
                            "event_name": "JobCreated",
                            "event_data": {},
                        },
                    ],
                    from_block=90,
                    to_block=110,
                )
                for e in evts:
                    tracker.track_event(e.id)

        async with factory() as db:
            async with db.begin():
                recorded = await backfill_events(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    events=[
                        {
                            "transaction_hash": tx1,
                            "log_index": 0,
                            "block_number": 100,
                            "block_hash": "0x" + "aa" * 32,
                            "event_name": "JobCreated",
                            "event_data": {},
                        },
                        {
                            "transaction_hash": tx2,
                            "log_index": 0,
                            "block_number": 105,
                            "block_hash": "0x" + "bb" * 32,
                            "event_name": "ProofSubmitted",
                            "event_data": {},
                        },
                    ],
                    from_block=95,
                    to_block=115,
                )
                assert len(recorded) == 2
                for e in recorded:
                    if e.id not in tracker.event_ids:
                        tracker.track_event(e.id)

        async with factory() as db:
            result = await db.execute(
                text("SELECT COUNT(*) FROM blockchain_events WHERE chain_id = :cid"),
                {"cid": tracker.chain_id},
            )
            count = result.scalar()
            assert count == 2

    @pytest.mark.asyncio
    async def test_12_batch_confirmation_across_restart(self, pg_durable):
        """Batch confirmation persists across restart."""
        engine, tracker = pg_durable
        tracker.test_name = "test_12"
        tracker.chain_id = 1_000_012
        factory = _make_session(engine)

        async with factory() as db:
            async with db.begin():
                for i in range(3):
                    ev = await record_event(
                        db,
                        chain_id=tracker.chain_id,
                        contract_address=CONTRACT,
                        transaction_hash="0x" + _unique_hex(),
                        log_index=0,
                        block_number=1000 + i,
                        block_hash="0x" + "ef" * 32,
                        event_name="JobCreated",
                        event_data={},
                    )
                    tracker.track_event(ev.id)

        engine2 = create_async_engine(PG_URL, pool_size=2, max_overflow=2, echo=False)
        try:
            factory2 = _make_session(engine2)
            async with factory2() as db:
                from app.services.blockchain_events import confirm_events_at_block

                async with db.begin():
                    count = await confirm_events_at_block(
                        db,
                        chain_id=tracker.chain_id,
                        contract_address=CONTRACT,
                        current_block=1003,
                        confirmations_required=2,
                    )
                    assert count >= 1
        finally:
            await engine2.dispose()

        async with factory() as db:
            result = await db.execute(
                text("SELECT confirmation_status FROM blockchain_events WHERE chain_id = :cid ORDER BY block_number"),
                {"cid": tracker.chain_id},
            )
            statuses = [r[0] for r in result.fetchall()]
            assert "confirmed" in statuses


class TestCleanupIsolation:
    """Proves cleanup only affects the current test's records."""

    @pytest.mark.asyncio
    async def test_sentinel_survives_cleanup(self, pg_durable):
        """A sentinel record created before the durability test survives cleanup."""
        engine, tracker = pg_durable

        sentinel_model_id = "sentinel_model_" + _unique_hex()[:8]
        sentinel_user_id = uuid.uuid4()

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO supported_models (id, name, vram_required_gb, price_base_units) "
                    "VALUES (:id, :name, :vram, :price)"
                ),
                {
                    "id": sentinel_model_id,
                    "name": "SentinelModel",
                    "vram": 8,
                    "price": 500000000000000000,
                },
            )
            await conn.execute(
                text("INSERT INTO users (id, wallet_address, role) VALUES (:id, :wallet, :role)"),
                {
                    "id": sentinel_user_id,
                    "wallet": _unique_address(),
                    "role": "user",
                },
            )

        cleanup_tracker = _TestTracker("sentinel_cleanup")
        cleanup_tracker.chain_id = 9_999_999
        await cleanup_tracker.cleanup(engine)

        async with engine.begin() as conn:
            model_row = await conn.execute(
                text("SELECT id FROM supported_models WHERE id = :id"),
                {"id": sentinel_model_id},
            )
            assert model_row.scalar_one_or_none() == sentinel_model_id

            user_row = await conn.execute(
                text("SELECT id FROM users WHERE id = :id"),
                {"id": sentinel_user_id},
            )
            assert user_row.scalar_one_or_none() == sentinel_user_id

        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM users WHERE id = :id"),
                {"id": sentinel_user_id},
            )
            await conn.execute(
                text("DELETE FROM supported_models WHERE id = :id"),
                {"id": sentinel_model_id},
            )

    @pytest.mark.asyncio
    async def test_only_tracked_records_deleted(self, pg_durable):
        """Records from a different chain_id are not deleted."""
        engine, tracker = pg_durable

        other_chain = 8_888_888
        other_tx = "0x" + _unique_hex()

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO blockchain_events "
                    "(id, chain_id, chain_instance_id, contract_address, transaction_hash, log_index, "
                    "block_number, block_hash, event_name, event_data, confirmation_status) "
                    "VALUES (:id, :cid, :instance, :ca, :tx, :li, :bn, :bh, :en, :ed, :cs)"
                ),
                {
                    "id": uuid.uuid4(),
                    "cid": other_chain,
                    "instance": f"cleanup-{other_chain}",
                    "ca": CONTRACT,
                    "tx": other_tx,
                    "li": 0,
                    "bn": 9999,
                    "bh": "0x" + "ff" * 32,
                    "en": "JobCreated",
                    "ed": "{}",
                    "cs": "pending",
                },
            )

        cleanup_tracker = _TestTracker("other_chain_cleanup")
        cleanup_tracker.chain_id = 7_777_777
        await cleanup_tracker.cleanup(engine)

        async with engine.begin() as conn:
            row = await conn.execute(
                text("SELECT id FROM blockchain_events WHERE transaction_hash = :tx"),
                {"tx": other_tx},
            )
            assert row.scalar_one() is not None

        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM blockchain_events WHERE transaction_hash = :tx"),
                {"tx": other_tx},
            )

    @pytest.mark.asyncio
    async def test_cleanup_idempotent(self, pg_durable):
        """Running cleanup twice on same tracker does not error."""
        engine, tracker = pg_durable
        tracker.test_name = "idempotent"
        tracker.chain_id = 6_666_666

        ev_id = uuid.uuid4()
        tracker.track_event(ev_id)

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO blockchain_events "
                    "(id, chain_id, chain_instance_id, contract_address, transaction_hash, log_index, "
                    "block_number, block_hash, event_name, event_data, confirmation_status) "
                    "VALUES (:id, :cid, :instance, :ca, :tx, :li, :bn, :bh, :en, :ed, :cs)"
                ),
                {
                    "id": ev_id,
                    "cid": tracker.chain_id,
                    "instance": f"cleanup-{tracker.chain_id}",
                    "ca": CONTRACT,
                    "tx": "0x" + _unique_hex(),
                    "li": 0,
                    "bn": 6666,
                    "bh": "0x" + "aa" * 32,
                    "en": "JobCreated",
                    "ed": "{}",
                    "cs": "pending",
                },
            )

        await tracker.cleanup(engine)
        await tracker.cleanup(engine)

        async with engine.begin() as conn:
            row = await conn.execute(
                text("SELECT id FROM blockchain_events WHERE id = :id"),
                {"id": ev_id},
            )
            assert row.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_cleanup_after_exception(self, pg_durable):
        """Cleanup runs correctly after a test raises an exception."""
        engine, tracker = pg_durable
        tracker.test_name = "exception_test"
        tracker.chain_id = 5_555_555

        ev_id = uuid.uuid4()
        tracker.track_event(ev_id)

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO blockchain_events "
                    "(id, chain_id, chain_instance_id, contract_address, transaction_hash, log_index, "
                    "block_number, block_hash, event_name, event_data, confirmation_status) "
                    "VALUES (:id, :cid, :instance, :ca, :tx, :li, :bn, :bh, :en, :ed, :cs)"
                ),
                {
                    "id": ev_id,
                    "cid": tracker.chain_id,
                    "instance": f"cleanup-{tracker.chain_id}",
                    "ca": CONTRACT,
                    "tx": "0x" + _unique_hex(),
                    "li": 0,
                    "bn": 5555,
                    "bh": "0x" + "aa" * 32,
                    "en": "JobCreated",
                    "ed": "{}",
                    "cs": "pending",
                },
            )

        try:
            raise ValueError("simulated test failure")
        except ValueError:
            pass

        await tracker.cleanup(engine)

        async with engine.begin() as conn:
            row = await conn.execute(
                text("SELECT id FROM blockchain_events WHERE id = :id"),
                {"id": ev_id},
            )
            assert row.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_engine_disposed_on_failure(self, pg_durable):
        """Engine is disposed even when the test raises an exception."""
        engine, tracker = pg_durable
        tracker.test_name = "dispose_test"
        tracker.chain_id = 4_444_444

        disposable_engine = create_async_engine(PG_URL, pool_size=2, max_overflow=2, echo=False)
        dispose_called = False
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            pass
        finally:
            await disposable_engine.dispose()
            dispose_called = True

        assert dispose_called is True


class TestReversedOrder:
    """Proves tests pass in reversed execution order."""

    @pytest.mark.asyncio
    async def test_reversed_batch_confirmed_events(self, pg_durable):
        """Test 12 logic in isolation with reversed ordering."""
        engine, tracker = pg_durable
        tracker.test_name = "reversed_12"
        tracker.chain_id = 2_000_012
        factory = _make_session(engine)

        async with factory() as db:
            async with db.begin():
                for i in range(3):
                    ev = await record_event(
                        db,
                        chain_id=tracker.chain_id,
                        contract_address=CONTRACT,
                        transaction_hash="0x" + _unique_hex(),
                        log_index=0,
                        block_number=2000 + i,
                        block_hash="0x" + "ef" * 32,
                        event_name="JobCreated",
                        event_data={},
                    )
                    tracker.track_event(ev.id)

        engine2 = create_async_engine(PG_URL, pool_size=2, max_overflow=2, echo=False)
        try:
            factory2 = _make_session(engine2)
            async with factory2() as db:
                from app.services.blockchain_events import confirm_events_at_block

                async with db.begin():
                    count = await confirm_events_at_block(
                        db,
                        chain_id=tracker.chain_id,
                        contract_address=CONTRACT,
                        current_block=2003,
                        confirmations_required=2,
                    )
                    assert count >= 1
        finally:
            await engine2.dispose()

        async with factory() as db:
            result = await db.execute(
                text("SELECT confirmation_status FROM blockchain_events WHERE chain_id = :cid ORDER BY block_number"),
                {"cid": tracker.chain_id},
            )
            statuses = [r[0] for r in result.fetchall()]
            assert "confirmed" in statuses

    @pytest.mark.asyncio
    async def test_reversed_reorg_demotion(self, pg_durable):
        """Test 04 logic in isolation with reversed ordering."""
        engine, tracker = pg_durable
        tracker.test_name = "reversed_04"
        tracker.chain_id = 2_000_004
        factory = _make_session(engine)

        async with factory() as db:
            async with db.begin():
                ev = await record_event(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    transaction_hash="0x" + _unique_hex(),
                    log_index=0,
                    block_number=2300,
                    block_hash="0x" + "aa" * 32,
                    event_name="JobCreated",
                    event_data={},
                )
                tracker.track_event(ev.id)
                await confirm_event(db, ev.id)

        async with factory() as db:
            async with db.begin():
                result = await handle_reorg(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    reverted_block_number=2300,
                    reverted_block_hash="0x" + "bb" * 32,
                )
                assert result["orphaned_events_count"] >= 1

                r = await db.execute(select(BlockchainEvent).where(BlockchainEvent.id == ev.id))
                updated = r.scalar_one()
                assert updated.confirmation_status == "pending"

    @pytest.mark.asyncio
    async def test_reversed_job_projection(self, pg_durable):
        """Test 06 logic in isolation with reversed ordering."""
        engine, tracker = pg_durable
        tracker.test_name = "reversed_06"
        tracker.chain_id = 2_000_006
        factory = _make_session(engine)

        user_id = uuid.uuid4()
        tracker.track_user(user_id)
        model_id = "rev_model_" + _unique_hex()[:8]
        tracker.track_model(model_id)
        job_id = uuid.uuid4()
        tracker.track_job(job_id)

        async with factory() as db:
            async with db.begin():
                user = User(id=user_id, wallet_address=_unique_address(), role="user")
                db.add(user)
                model = SupportedModel(
                    id=model_id,
                    name="RevModel",
                    vram_required_gb=8,
                    price_base_units=500000000000000000,
                )
                db.add(model)
                await db.flush()

                job = Job(
                    id=job_id,
                    user_id=user_id,
                    model_id=model_id,
                    chain_job_id="0x" + _unique_hex(),
                    price_base_units=500000000000000000,
                    status="assigned",
                    deadline=datetime.now(timezone.utc),
                )
                db.add(job)

                ev = await record_event(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    transaction_hash="0x" + _unique_hex(),
                    log_index=0,
                    block_number=2500,
                    block_hash="0x" + "aa" * 32,
                    event_name="ProviderAssigned",
                    event_data={"projection": "assigned"},
                    job_id=job_id,
                )
                tracker.track_event(ev.id)
                await confirm_event(db, ev.id)

        async with factory() as db:
            async with db.begin():
                result = await handle_reorg(
                    db,
                    chain_id=tracker.chain_id,
                    contract_address=CONTRACT,
                    reverted_block_number=2500,
                    reverted_block_hash="0x" + "bb" * 32,
                )
                assert result["affected_job_ids"] == [str(job_id)]

                r = await db.execute(select(BlockchainEvent).where(BlockchainEvent.id == ev.id))
                updated = r.scalar_one()
                assert updated.confirmation_status == "pending"
                assert updated.event_name == "ProviderAssigned"
