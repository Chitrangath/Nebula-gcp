"""PostgreSQL Integration Tests — Phase 2 Migration Verification

Requires:
  - Running PostgreSQL 17 container at localhost:5433
  - DATABASE_URL environment variable pointing to the nebula_test database
  - NEVER commit credentials; always use env vars

IMPORTANT: These tests MUST run against PostgreSQL, not SQLite.

Design: This module NEVER imports from ``app.*`` and NEVER mutates
``sys.modules``.  It reads DATABASE_URL straight from the environment and
uses raw SQLAlchemy engines so that collection-time side-effects cannot
corrupt other test modules in the same pytest invocation.
"""

import os
import subprocess
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── PG availability gate ────────────────────────────────────────

_raw_db_url = os.environ.get("DATABASE_URL", "")
_pg_reason = None
if not _raw_db_url:
    _pg_reason = "DATABASE_URL environment variable is not set"
else:
    try:
        _parsed = urlparse(_raw_db_url)
        _db_name = _parsed.path.lstrip("/")
        if "postgresql" not in _parsed.scheme:
            _pg_reason = f"DATABASE_URL must use postgresql scheme, got '{_parsed.scheme}'"
        elif _db_name != "nebula_test":
            _pg_reason = f"DATABASE_URL must target 'nebula_test' database, got '{_db_name}'"
    except Exception as exc:
        _pg_reason = f"Cannot parse DATABASE_URL: {exc}"
    finally:
        del _parsed, _db_name

PG_URL = _raw_db_url

if _pg_reason:
    pytestmark = pytest.mark.skip(reason=f"PostgreSQL not available: {_pg_reason}")
del _pg_reason, _raw_db_url


# ── Helpers ─────────────────────────────────────────────────────


def run_alembic(*args: str) -> subprocess.CompletedProcess:
    """Run alembic command from the backend directory."""
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    result = subprocess.run(
        ["uv", "run", "alembic"] + list(args),
        cwd=backend_dir,
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    return result


async def _reset_db(engine):
    """Drop and recreate the public schema."""
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def restore_migrated_schema_after_module():
    """Leave the shared test database migrated for suites that run afterward."""
    yield
    result = run_alembic("upgrade", "head")
    assert result.returncode == 0, f"Final schema restore failed: {result.stderr}"


@pytest_asyncio.fixture
async def pg_engine():
    """Per-test PostgreSQL engine (dialect verified)."""
    engine = create_async_engine(PG_URL, echo=False)
    async with engine.connect() as conn:
        dialect = conn.dialect.name
        assert dialect == "postgresql", f"Expected postgresql, got {dialect}"
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_conn(pg_engine):
    """Per-test raw connection."""
    async with pg_engine.connect() as conn:
        yield conn


@pytest_asyncio.fixture
async def pg_session(pg_engine):
    """Per-test session with rollback."""
    session_factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def pg_with_tables(pg_engine):
    """Ensures all application tables exist via alembic upgrade head."""
    await _reset_db(pg_engine)
    result = run_alembic("upgrade", "head")
    assert result.returncode == 0, f"Upgrade failed: {result.stderr}"
    yield pg_engine
    await _reset_db(pg_engine)


@pytest_asyncio.fixture
async def pg_empty(pg_engine):
    """Ensures database is empty (no application tables)."""
    await _reset_db(pg_engine)
    yield pg_engine


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

WALLET_OK = "0x" + "a" * 40
WALLET_OK_2 = "0x" + "b" * 40
MODEL_ID = "test_model"
MODEL_PRICE = 50000


async def _seed_user(conn, wallet=WALLET_OK):
    await conn.execute(
        text("INSERT INTO users (wallet_address, role) VALUES (:w, 'user')"),
        {"w": wallet},
    )
    r = await conn.execute(text("SELECT id FROM users ORDER BY created_at LIMIT 1"))
    return r.fetchone()[0]


async def _seed_model(conn, model_id=MODEL_ID, price=MODEL_PRICE):
    await conn.execute(
        text("INSERT INTO supported_models (id, name, price_base_units) VALUES (:id, 'Test', :p)"),
        {"id": model_id, "p": price},
    )


async def _seed_job(conn, user_id, model_id=MODEL_ID, price=MODEL_PRICE, chain_job_id=None):
    if chain_job_id is None:
        chain_job_id = "0x" + "c" * 64
    await conn.execute(
        text(
            "INSERT INTO jobs (user_id, model_id, chain_job_id, price_base_units, deadline) "
            "VALUES (:uid, :mid, :cid, :p, now() + interval '1 hour')"
        ),
        {"uid": user_id, "mid": model_id, "cid": chain_job_id, "p": price},
    )
    r = await conn.execute(text("SELECT id FROM jobs ORDER BY created_at LIMIT 1"))
    return r.fetchone()[0]


async def _seed_node(conn, user_id, api_hash="aa" * 32):
    await conn.execute(
        text("INSERT INTO nodes (provider_id, api_key_hash) VALUES (:uid, :kh)"),
        {"uid": user_id, "kh": api_hash},
    )
    r = await conn.execute(text("SELECT id FROM nodes ORDER BY created_at LIMIT 1"))
    return r.fetchone()[0]


async def _seed_lease(conn, job_id, node_id, lease_id="0x" + "d" * 64, status="active"):
    await conn.execute(
        text(
            "INSERT INTO leases (job_id, node_id, lease_id, expires_at, status) "
            "VALUES (:jid, :nid, :lid, now() + interval '1 hour', :st)"
        ),
        {"jid": job_id, "nid": node_id, "lid": lease_id, "st": status},
    )
    r = await conn.execute(text("SELECT id FROM leases ORDER BY created_at LIMIT 1"))
    return r.fetchone()[0]


# ──────────────────────────────────────────────
# Test 1: Alembic has exactly one head
# ──────────────────────────────────────────────


class TestAlembicHeads:
    @pytest.mark.asyncio
    async def test_single_head(self):
        result = run_alembic("heads")
        assert result.returncode == 0, f"alembic heads failed: {result.stderr}"
        lines = [ln.strip() for ln in result.stdout.strip().splitlines() if ln.strip()]
        assert len(lines) == 1, f"Expected 1 head, got {len(lines)}: {lines}"
        assert "0009_payment_withdrawal_history" in lines[0]


# ──────────────────────────────────────────────
# Tests 2-4: Upgrade creates all application tables
# ──────────────────────────────────────────────


class TestUpgradeCreatesTables:
    @pytest.mark.asyncio
    async def test_upgrade_from_empty_succeeds(self, pg_empty):
        result = run_alembic("upgrade", "head")
        assert result.returncode == 0, f"Upgrade failed: {result.stderr}"
        output = result.stdout + result.stderr
        assert "Running upgrade" in output or "already exist" in output

    @pytest.mark.asyncio
    async def test_exactly_15_application_tables_created(self, pg_with_tables, pg_conn):
        r = await pg_conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                "AND table_name != 'alembic_version' ORDER BY table_name"
            )
        )
        tables = sorted([row[0] for row in r.fetchall()])
        expected = sorted(
            [
                "users",
                "supported_models",
                "nodes",
                "jobs",
                "payments",
                "auth_challenges",
                "auth_sessions",
                "leases",
                "job_attempts",
                "proofs",
                "chain_transactions",
                "blockchain_events",
                "chain_cursors",
                "reconciliation_incidents",
                "signer_nonces",
            ]
        )
        assert tables == expected, f"Expected {expected}, got {tables}"

    @pytest.mark.asyncio
    async def test_alembic_version_records_head(self, pg_with_tables, pg_conn):
        r = await pg_conn.execute(text("SELECT version_num FROM alembic_version"))
        row = r.fetchone()
        assert row is not None, "alembic_version table is empty"
        assert row[0] == "0009_payment_withdrawal_history"


# ──────────────────────────────────────────────
# Tests 5-6: Downgrade and re-upgrade
# ──────────────────────────────────────────────


class TestDowngradeReupgrade:
    @pytest.mark.asyncio
    async def test_downgrade_removes_all_application_tables(self, pg_with_tables, pg_conn):
        result = run_alembic("downgrade", "base")
        assert result.returncode == 0, f"Downgrade failed: {result.stderr}"
        r = await pg_conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                "AND table_name != 'alembic_version'"
            )
        )
        tables = [row[0] for row in r.fetchall()]
        assert len(tables) == 0, f"Expected 0 application tables, got: {tables}"
        # Re-upgrade for subsequent tests
        result = run_alembic("upgrade", "head")
        assert result.returncode == 0, f"Re-upgrade failed: {result.stderr}"

    @pytest.mark.asyncio
    async def test_reupgrade_from_base_succeeds(self, pg_with_tables, pg_conn):
        result = run_alembic("downgrade", "base")
        assert result.returncode == 0, f"Downgrade failed: {result.stderr}"
        result = run_alembic("upgrade", "head")
        assert result.returncode == 0, f"Re-upgrade failed: {result.stderr}"
        r = await pg_conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                "AND table_name != 'alembic_version'"
            )
        )
        tables = [row[0] for row in r.fetchall()]
        assert len(tables) == 15, f"Expected 15 tables after re-upgrade, got {len(tables)}"


# ──────────────────────────────────────────────
# Test 7: All foreign keys exist
# ──────────────────────────────────────────────


class TestForeignKeys:
    @pytest.mark.asyncio
    async def test_all_foreign_keys_exist(self, pg_with_tables, pg_conn):
        r = await pg_conn.execute(
            text(
                "SELECT tc.table_name, kcu.column_name, "
                "ccu.table_name AS foreign_table, ccu.column_name AS foreign_column "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu "
                "ON ccu.constraint_name = tc.constraint_name "
                "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public' "
                "ORDER BY tc.table_name, kcu.column_name"
            )
        )
        fks = {(row[0], row[1], row[2], row[3]) for row in r.fetchall()}
        expected_fks = {
            ("auth_sessions", "user_id", "users", "id"),
            ("blockchain_events", "job_id", "jobs", "id"),
            ("chain_transactions", "job_id", "jobs", "id"),
            ("job_attempts", "job_id", "jobs", "id"),
            ("job_attempts", "node_id", "nodes", "id"),
            ("job_attempts", "lease_id", "leases", "id"),
            ("jobs", "user_id", "users", "id"),
            ("jobs", "model_id", "supported_models", "id"),
            ("jobs", "assigned_node_id", "nodes", "id"),
            ("leases", "job_id", "jobs", "id"),
            ("leases", "node_id", "nodes", "id"),
            ("nodes", "provider_id", "users", "id"),
            ("payments", "job_id", "jobs", "id"),
            ("payments", "user_id", "users", "id"),
            ("payments", "provider_id", "users", "id"),
            ("proofs", "job_attempt_id", "job_attempts", "id"),
        }
        missing = expected_fks - fks
        assert not missing, f"Missing foreign keys: {missing}"


# ──────────────────────────────────────────────
# Tests 8-9: Job and lease status constraints
# ──────────────────────────────────────────────


class TestStatusConstraints:
    @pytest.mark.asyncio
    async def test_job_status_constraint_rejects_invalid(self, pg_with_tables, pg_conn):
        user_id = await _seed_user(pg_conn, WALLET_OK)
        await _seed_model(pg_conn)
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text(
                    "INSERT INTO jobs (user_id, model_id, chain_job_id, price_base_units, deadline, status) "
                    "VALUES (:uid, 'test_model', '0x' || repeat('b', 64), 50000, "
                    "now() + interval '1 hour', 'invalid_status')"
                ),
                {"uid": user_id},
            )
        await pg_conn.rollback()

    @pytest.mark.asyncio
    async def test_lease_status_constraint_rejects_invalid(self, pg_with_tables, pg_conn):
        user_id = await _seed_user(pg_conn, WALLET_OK)
        await _seed_model(pg_conn)
        job_id = await _seed_job(pg_conn, user_id)
        node_id = await _seed_node(pg_conn, user_id)
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text(
                    "INSERT INTO leases (job_id, node_id, lease_id, expires_at, status) "
                    "VALUES (:jid, :nid, '0x' || repeat('f', 64), "
                    "now() + interval '1 hour', 'invalid_lease_status')"
                ),
                {"jid": job_id, "nid": node_id},
            )
        await pg_conn.rollback()


# ──────────────────────────────────────────────
# Test 10: Only one pending_chain or active lease per job
# ──────────────────────────────────────────────


class TestLeaseUniqueness:
    @pytest.mark.asyncio
    async def test_only_one_active_lease_per_job(self, pg_with_tables, pg_conn):
        user_id = await _seed_user(pg_conn, WALLET_OK)
        await _seed_model(pg_conn)
        job_id = await _seed_job(pg_conn, user_id)
        node_id = await _seed_node(pg_conn, user_id)
        await _seed_lease(pg_conn, job_id, node_id, "0x" + "j" * 64, "active")
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text(
                    "INSERT INTO leases (job_id, node_id, lease_id, expires_at, status) "
                    "VALUES (:jid, :nid, '0x' || repeat('k', 64), "
                    "now() + interval '1 hour', 'active')"
                ),
                {"jid": job_id, "nid": node_id},
            )
        await pg_conn.rollback()


# ──────────────────────────────────────────────
# Test 11: New lease allowed after prior expires
# ──────────────────────────────────────────────


class TestLeaseAfterExpiry:
    @pytest.mark.asyncio
    async def test_new_lease_after_prior_expired(self, pg_with_tables, pg_conn):
        user_id = await _seed_user(pg_conn, WALLET_OK)
        await _seed_model(pg_conn)
        job_id = await _seed_job(pg_conn, user_id)
        node_id = await _seed_node(pg_conn, user_id)
        await _seed_lease(pg_conn, job_id, node_id, "0x" + "o" * 64, "expired")
        await _seed_lease(pg_conn, job_id, node_id, "0x" + "p" * 64, "active")
        await pg_conn.rollback()


# ──────────────────────────────────────────────
# Test 12: Duplicate (job_id, attempt_number) rejected
# ──────────────────────────────────────────────


class TestAttemptUniqueness:
    @pytest.mark.asyncio
    async def test_duplicate_attempt_number_rejected(self, pg_with_tables, pg_conn):
        user_id = await _seed_user(pg_conn, WALLET_OK)
        await _seed_model(pg_conn)
        job_id = await _seed_job(pg_conn, user_id)
        node_id = await _seed_node(pg_conn, user_id)
        lease_id = await _seed_lease(pg_conn, job_id, node_id, "0x" + "t" * 64)
        await pg_conn.execute(
            text("INSERT INTO job_attempts (job_id, node_id, lease_id, attempt_number) VALUES (:jid, :nid, :lid, 1)"),
            {"jid": job_id, "nid": node_id, "lid": lease_id},
        )
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text(
                    "INSERT INTO job_attempts (job_id, node_id, lease_id, attempt_number) VALUES (:jid, :nid, :lid, 1)"
                ),
                {"jid": job_id, "nid": node_id, "lid": lease_id},
            )
        await pg_conn.rollback()


# ──────────────────────────────────────────────
# Test 13: Duplicate blockchain event identity rejected
# ──────────────────────────────────────────────


class TestBlockchainEventUniqueness:
    @pytest.mark.asyncio
    async def test_duplicate_event_identity_rejected(self, pg_with_tables, pg_conn):
        await pg_conn.execute(
            text(
                "INSERT INTO blockchain_events "
                "(chain_id, chain_instance_id, contract_address, transaction_hash, log_index, "
                "block_number, block_hash, event_name) "
                "VALUES (421614, '0x' || repeat('1', 64), '0x' || repeat('a', 40), "
                "'0x' || repeat('b', 64), "
                "0, 100, '0x' || repeat('c', 64), 'JobCreated')"
            )
        )
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text(
                    "INSERT INTO blockchain_events "
                    "(chain_id, chain_instance_id, contract_address, transaction_hash, log_index, "
                    "block_number, block_hash, event_name) "
                    "VALUES (421614, '0x' || repeat('1', 64), '0x' || repeat('a', 40), "
                    "'0x' || repeat('b', 64), "
                    "0, 100, '0x' || repeat('c', 64), 'JobCreated')"
                )
            )
        await pg_conn.rollback()


# ──────────────────────────────────────────────
# Test 14: Different events from same tx with different log_index
# ──────────────────────────────────────────────


class TestMultipleEventsPerTx:
    @pytest.mark.asyncio
    async def test_different_log_index_allowed(self, pg_with_tables, pg_conn):
        await pg_conn.execute(
            text(
                "INSERT INTO blockchain_events "
                "(chain_id, chain_instance_id, contract_address, transaction_hash, log_index, "
                "block_number, block_hash, event_name) "
                "VALUES (421614, '0x' || repeat('2', 64), '0x' || repeat('d', 40), "
                "'0x' || repeat('e', 64), "
                "0, 100, '0x' || repeat('f', 64), 'JobCreated')"
            )
        )
        await pg_conn.execute(
            text(
                "INSERT INTO blockchain_events "
                "(chain_id, chain_instance_id, contract_address, transaction_hash, log_index, "
                "block_number, block_hash, event_name) "
                "VALUES (421614, '0x' || repeat('2', 64), '0x' || repeat('d', 40), "
                "'0x' || repeat('e', 64), "
                "1, 100, '0x' || repeat('f', 64), 'ProviderAssigned')"
            )
        )
        await pg_conn.rollback()


# ──────────────────────────────────────────────
# Test 15: NUMERIC(78,0) accepts large amounts
# ──────────────────────────────────────────────


class TestNumericPrecision:
    @pytest.mark.asyncio
    async def test_numeric_78_accepts_large_amount(self, pg_with_tables, pg_conn):
        large_amount = 10**77
        await pg_conn.execute(
            text("INSERT INTO supported_models (id, name, price_base_units) VALUES ('large_model', 'Large', :amt)"),
            {"amt": large_amount},
        )
        r = await pg_conn.execute(text("SELECT price_base_units FROM supported_models WHERE id = 'large_model'"))
        result = r.fetchone()[0]
        assert int(result) == large_amount
        await pg_conn.rollback()


# ──────────────────────────────────────────────
# Tests 16a-16f: Monetary constraints
# ──────────────────────────────────────────────


class TestMonetaryConstraints:
    @pytest.mark.asyncio
    async def test_negative_supported_model_price_rejected(self, pg_with_tables, pg_conn):
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text("INSERT INTO supported_models (id, name, price_base_units) VALUES ('neg', 'Neg', -50000)")
            )
        await pg_conn.rollback()

    @pytest.mark.asyncio
    async def test_zero_supported_model_price_rejected(self, pg_with_tables, pg_conn):
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text("INSERT INTO supported_models (id, name, price_base_units) VALUES ('zero', 'Zero', 0)")
            )
        await pg_conn.rollback()

    @pytest.mark.asyncio
    async def test_positive_supported_model_price_accepted(self, pg_with_tables, pg_conn):
        await pg_conn.execute(
            text("INSERT INTO supported_models (id, name, price_base_units) VALUES ('pos', 'Pos', 1)")
        )
        await pg_conn.rollback()

    @pytest.mark.asyncio
    async def test_negative_job_price_rejected(self, pg_with_tables, pg_conn):
        user_id = await _seed_user(pg_conn)
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text(
                    "INSERT INTO jobs (user_id, model_id, chain_job_id, price_base_units, deadline) "
                    "VALUES (:uid, 'm', '0x' || repeat('a', 64), -1, now() + interval '1 hour')"
                ),
                {"uid": user_id},
            )
        await pg_conn.rollback()

    @pytest.mark.asyncio
    async def test_zero_job_price_rejected(self, pg_with_tables, pg_conn):
        user_id = await _seed_user(pg_conn)
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text(
                    "INSERT INTO jobs (user_id, model_id, chain_job_id, price_base_units, deadline) "
                    "VALUES (:uid, 'm', '0x' || repeat('a', 64), 0, now() + interval '1 hour')"
                ),
                {"uid": user_id},
            )
        await pg_conn.rollback()

    @pytest.mark.asyncio
    async def test_negative_escrow_rejected(self, pg_with_tables, pg_conn):
        user_id = await _seed_user(pg_conn)
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text(
                    "INSERT INTO jobs (user_id, model_id, chain_job_id, price_base_units, "
                    "blockchain_escrow_amount, deadline) "
                    "VALUES (:uid, 'm', '0x' || repeat('a', 64), 50000, -1, now() + interval '1 hour')"
                ),
                {"uid": user_id},
            )
        await pg_conn.rollback()

    @pytest.mark.asyncio
    async def test_null_escrow_accepted(self, pg_with_tables, pg_conn):
        user_id = await _seed_user(pg_conn)
        await _seed_model(pg_conn)
        await _seed_job(pg_conn, user_id)
        await pg_conn.rollback()

    @pytest.mark.asyncio
    async def test_negative_payment_amount_rejected(self, pg_with_tables, pg_conn):
        user_id = await _seed_user(pg_conn)
        await _seed_model(pg_conn)
        job_id = await _seed_job(pg_conn, user_id)
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text("INSERT INTO payments (job_id, user_id, amount_base_units) VALUES (:jid, :uid, -1)"),
                {"jid": job_id, "uid": user_id},
            )
        await pg_conn.execute(text("ROLLBACK"))

    @pytest.mark.asyncio
    async def test_zero_payment_amount_rejected(self, pg_with_tables, pg_conn):
        user_id = await _seed_user(pg_conn)
        await _seed_model(pg_conn)
        job_id = await _seed_job(pg_conn, user_id)
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text("INSERT INTO payments (job_id, user_id, amount_base_units) VALUES (:jid, :uid, 0)"),
                {"jid": job_id, "uid": user_id},
            )
        await pg_conn.execute(text("ROLLBACK"))

    @pytest.mark.asyncio
    async def test_negative_chain_tx_amount_rejected(self, pg_with_tables, pg_conn):
        await pg_conn.execute(
            text(
                "INSERT INTO chain_transactions "
                "(chain_id, contract_address, tx_hash, tx_type, from_address, to_address) "
                "VALUES (421614, '0x' || repeat('a', 40), '0x' || repeat('b', 64), "
                "'createJob', '0x' || repeat('c', 40), '0x' || repeat('d', 40))"
            )
        )
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text(
                    "INSERT INTO chain_transactions "
                    "(chain_id, contract_address, tx_hash, tx_type, from_address, to_address, amount_base_units) "
                    "VALUES (421614, '0x' || repeat('a', 40), '0x' || repeat('e', 64), "
                    "'createJob', '0x' || repeat('c', 40), '0x' || repeat('d', 40), -1)"
                )
            )
        await pg_conn.execute(text("ROLLBACK"))

    @pytest.mark.asyncio
    async def test_zero_chain_tx_amount_accepted(self, pg_with_tables, pg_conn):
        await pg_conn.execute(
            text(
                "INSERT INTO chain_transactions "
                "(chain_id, contract_address, tx_hash, tx_type, from_address, to_address, amount_base_units) "
                "VALUES (421614, '0x' || repeat('a', 40), '0x' || repeat('b', 64), "
                "'createJob', '0x' || repeat('c', 40), '0x' || repeat('d', 40), 0)"
            )
        )
        await pg_conn.rollback()

    @pytest.mark.asyncio
    async def test_null_chain_tx_amount_accepted(self, pg_with_tables, pg_conn):
        await pg_conn.execute(
            text(
                "INSERT INTO chain_transactions "
                "(chain_id, contract_address, tx_hash, tx_type, from_address, to_address) "
                "VALUES (421614, '0x' || repeat('a', 40), '0x' || repeat('b', 64), "
                "'submitProof', '0x' || repeat('c', 40), '0x' || repeat('d', 40))"
            )
        )
        await pg_conn.rollback()


# ──────────────────────────────────────────────
# Test 17: Wallet address format and normalization
# ──────────────────────────────────────────────


class TestWalletNormalization:
    @pytest.mark.asyncio
    async def test_duplicate_wallet_rejected(self, pg_with_tables, pg_conn):
        wallet = "0x" + "a" * 40
        await pg_conn.execute(
            text("INSERT INTO users (wallet_address, role) VALUES (:w, 'user')"),
            {"w": wallet},
        )
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text("INSERT INTO users (wallet_address, role) VALUES (:w, 'user')"),
                {"w": wallet},
            )
        await pg_conn.execute(text("ROLLBACK"))

    @pytest.mark.asyncio
    async def test_uppercase_wallet_rejected(self, pg_with_tables, pg_conn):
        """Uppercase hex fails the lowercase CHECK constraint."""
        wallet_upper = "0x" + "A" * 40
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text("INSERT INTO users (wallet_address, role) VALUES (:w, 'user')"),
                {"w": wallet_upper},
            )
        await pg_conn.execute(text("ROLLBACK"))

    @pytest.mark.asyncio
    async def test_mixed_case_wallet_rejected(self, pg_with_tables, pg_conn):
        wallet_mixed = "0x" + "aAbBcC" * 6 + "dD"
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text("INSERT INTO users (wallet_address, role) VALUES (:w, 'user')"),
                {"w": wallet_mixed},
            )
        await pg_conn.execute(text("ROLLBACK"))

    @pytest.mark.asyncio
    async def test_uppercase_and_lowercase_same_address_not_two_users(self, pg_with_tables, pg_conn):
        """Lowercase + uppercase of same address must not create two users.
        The uppercase insert fails the CHECK; only one row exists."""
        wallet_lo = "0x" + "a" * 40
        wallet_hi = "0x" + "A" * 40
        await pg_conn.execute(
            text("INSERT INTO users (wallet_address, role) VALUES (:w, 'user')"),
            {"w": wallet_lo},
        )
        await pg_conn.execute(text("SAVEPOINT sp_uppercase"))
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text("INSERT INTO users (wallet_address, role) VALUES (:w, 'user')"),
                {"w": wallet_hi},
            )
        await pg_conn.execute(text("ROLLBACK TO SAVEPOINT sp_uppercase"))
        r = await pg_conn.execute(text("SELECT COUNT(*) FROM users"))
        count = r.fetchone()[0]
        assert count == 1, f"Expected 1 user, got {count}"
        await pg_conn.execute(text("ROLLBACK"))

    @pytest.mark.asyncio
    async def test_invalid_wallet_length_rejected(self, pg_with_tables, pg_conn):
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text("INSERT INTO users (wallet_address, role) VALUES (:w, 'user')"),
                {"w": "0x" + "a" * 38},
            )
        await pg_conn.execute(text("ROLLBACK"))

    @pytest.mark.asyncio
    async def test_no_0x_prefix_rejected(self, pg_with_tables, pg_conn):
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text("INSERT INTO users (wallet_address, role) VALUES (:w, 'user')"),
                {"w": "a" * 40},
            )
        await pg_conn.execute(text("ROLLBACK"))


# ──────────────────────────────────────────────
# Test 18: No plaintext refresh tokens or API keys
# ──────────────────────────────────────────────


class TestNoPlaintextSecrets:
    @pytest.mark.asyncio
    async def test_no_plaintext_refresh_token_column(self, pg_with_tables, pg_conn):
        r = await pg_conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'auth_sessions'"
            )
        )
        columns = {row[0] for row in r.fetchall()}
        assert "refresh_token" not in columns, "auth_sessions has plaintext refresh_token column"
        assert "refresh_token_hash" in columns, "auth_sessions missing refresh_token_hash column"

    @pytest.mark.asyncio
    async def test_no_plaintext_api_key_column(self, pg_with_tables, pg_conn):
        r = await pg_conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'nodes'"
            )
        )
        columns = {row[0] for row in r.fetchall()}
        assert "api_key" not in columns, "nodes has plaintext api_key column"
        assert "api_key_hash" in columns, "nodes missing api_key_hash column"


# ──────────────────────────────────────────────
# Test 19: Invalid foreign key references rejected
# ──────────────────────────────────────────────


class TestForeignKeyRejection:
    @pytest.mark.asyncio
    async def test_invalid_user_id_in_job_rejected(self, pg_with_tables, pg_conn):
        import uuid

        fake_user_id = str(uuid.uuid4())
        await pg_conn.execute(
            text("INSERT INTO supported_models (id, name, price_base_units) VALUES ('fk_model', 'FK Model', 50000)")
        )
        with pytest.raises(IntegrityError):
            await pg_conn.execute(
                text(
                    "INSERT INTO jobs (user_id, model_id, chain_job_id, price_base_units, deadline) "
                    "VALUES (:uid, 'fk_model', '0x' || repeat('x', 64), "
                    "50000, now() + interval '1 hour')"
                ),
                {"uid": fake_user_id},
            )
        await pg_conn.rollback()


# ──────────────────────────────────────────────
# Test 20: Downgrade 0002 → 0001 and re-upgrade
# ──────────────────────────────────────────────


class TestDowngradeUpgrade0002:
    @pytest.mark.asyncio
    async def test_downgrade_0002_to_0001_removes_new_constraints(self, pg_with_tables, pg_conn):
        """After downgrade, the 0002-specific constraints must not exist."""
        result = run_alembic("downgrade", "0001_initial_schema")
        assert result.returncode == 0, f"Downgrade failed: {result.stderr}"
        r = await pg_conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE contype = 'c' AND connamespace = 'public'::regnamespace "
                "AND conname LIKE 'ck_%_positive' OR conname LIKE 'ck_%_lowercase%'"
            )
        )
        remaining = {row[0] for row in r.fetchall()}
        # These must be gone
        expected_gone = {
            "ck_supported_models_price_positive",
            "ck_jobs_price_positive",
            "ck_jobs_escrow_positive_or_null",
            "ck_payments_amount_positive",
            "ck_chain_tx_amount_non_negative_or_null",
            "ck_users_wallet_lowercase_hex",
            "ck_auth_challenges_wallet_lowercase_hex",
        }
        assert not (expected_gone & remaining), (
            f"Constraints still present after downgrade: {expected_gone & remaining}"
        )
        # Re-upgrade
        result = run_alembic("upgrade", "head")
        assert result.returncode == 0, f"Re-upgrade failed: {result.stderr}"

    @pytest.mark.asyncio
    async def test_reupgrade_restores_constraints(self, pg_with_tables, pg_conn):
        """After downgrade+re-upgrade, all 0002 constraints must exist again."""
        result = run_alembic("downgrade", "0001_initial_schema")
        assert result.returncode == 0
        result = run_alembic("upgrade", "head")
        assert result.returncode == 0
        r = await pg_conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE contype = 'c' AND connamespace = 'public'::regnamespace "
                "AND conname IN ("
                "'ck_supported_models_price_positive', "
                "'ck_jobs_price_positive', "
                "'ck_jobs_escrow_positive_or_null', "
                "'ck_payments_amount_positive', "
                "'ck_chain_tx_amount_non_negative_or_null', "
                "'ck_users_wallet_lowercase_hex', "
                "'ck_auth_challenges_wallet_lowercase_hex'"
                ")"
            )
        )
        names = {row[0] for row in r.fetchall()}
        expected = {
            "ck_supported_models_price_positive",
            "ck_jobs_price_positive",
            "ck_jobs_escrow_positive_or_null",
            "ck_payments_amount_positive",
            "ck_chain_tx_amount_non_negative_or_null",
            "ck_users_wallet_lowercase_hex",
            "ck_auth_challenges_wallet_lowercase_hex",
        }
        missing = expected - names
        assert not missing, f"Constraints missing after re-upgrade: {missing}"


# ──────────────────────────────────────────────
# Test 22: Lease partial-index predicate verification
# ──────────────────────────────────────────────


class TestLeaseIndexPredicate:
    @pytest.mark.asyncio
    async def test_partial_index_covers_active_and_pending_chain(self, pg_with_tables, pg_conn):
        """Verify the lease partial unique index WHERE clause covers both
        'active' and 'pending_chain' statuses."""
        r = await pg_conn.execute(
            text(
                "SELECT indexname, indexdef "
                "FROM pg_indexes "
                "WHERE schemaname = 'public' "
                "AND tablename = 'leases' "
                "AND indexname = 'idx_one_live_lease_per_job'"
            )
        )
        row = r.fetchone()
        assert row is not None, "Partial unique index 'idx_one_live_lease_per_job' not found on leases table"
        indexdef = row[1]
        assert "active" in indexdef, f"Index WHERE clause missing 'active': {indexdef}"
        assert "pending_chain" in indexdef, f"Index WHERE clause missing 'pending_chain': {indexdef}"
        assert "job_id" in indexdef, f"Index must cover job_id: {indexdef}"


# ──────────────────────────────────────────────
# Test 21: PostgreSQL dialect check
# ──────────────────────────────────────────────


class TestPostgreSQLDialect:
    @pytest.mark.asyncio
    async def test_engine_dialect_is_postgresql(self, pg_engine):
        async with pg_engine.connect() as conn:
            assert conn.dialect.name == "postgresql", (
                f"PostgreSQL suite requires postgresql dialect, got {conn.dialect.name}"
            )
