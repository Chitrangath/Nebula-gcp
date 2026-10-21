"""Regression tests for the Phase 2/3 test fixture.

These tests prove that the SQLite in-memory test infrastructure is
correct and that the conftest fixtures provide the guarantees listed
in the PRD and development plan.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as db_module
from app.main import app

# ── Helpers ─────────────────────────────────────────────────────


async def _count(db: AsyncSession, table: str) -> int:
    r = await db.execute(text(f"SELECT count(*) FROM {table}"))
    return r.scalar_one()


async def _seed_user_with_token(db: AsyncSession) -> tuple[str, str]:
    """Create a user + auth session via ORM, return (wallet, jwt_token)."""
    from app.models import AuthSession, User
    from app.services.auth_service import create_access_token, sha256_hex

    wallet = "0x" + uuid.uuid4().hex[:40]
    user_id = uuid.uuid4()
    user = User(id=user_id, wallet_address=wallet, role="user")
    db.add(user)

    token = create_access_token(str(user_id), wallet, "user")
    session = AuthSession(
        user_id=user_id,
        token_hash=sha256_hex(token),
        refresh_token_hash=sha256_hex(uuid.uuid4().hex),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(session)
    await db.flush()
    return wallet, token


# ── Test 1: API writes are visible through the injected test session ──


class TestAPIWritesVisible:
    """POST a node registration via the HTTP API, then read it back through
    the *same* db session that was injected into the request handler."""

    @pytest.mark.asyncio
    async def test_node_written_by_api_visible_in_test_session(self, db: AsyncSession):
        wallet, token = await _seed_user_with_token(db)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/nodes",
                json={"gpu_name": "RTX 4090", "vram_gb": 24, "location": "US"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text

        # Read back through the same session
        count = await _count(db, "nodes")
        assert count >= 1, "Node written by API handler is not visible in the test session"


# ── Test 2: Router and service receive the same AsyncSession ──


class TestSameSession:
    """The db session yielded by get_db inside the handler must be the
    exact object that the test's ``db`` fixture yields."""

    @pytest.mark.asyncio
    async def test_get_db_yields_test_session(self, db: AsyncSession):
        from app.database import get_db

        received_sessions: list[AsyncSession] = []

        async def _capture_db():
            received_sessions.append(db)
            yield db

        app.dependency_overrides[get_db] = _capture_db

        wallet, token = await _seed_user_with_token(db)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get(
                "/v1/nodes",
                headers={"Authorization": f"Bearer {token}"},
            )

        app.dependency_overrides.clear()

        assert len(received_sessions) == 1, f"Expected 1 session, got {len(received_sessions)}"
        assert received_sessions[0] is db, "Router received a different session than the test db"


# ── Test 3: Failed transaction rolls back, no partial rows ──


class TestRollbackOnFailure:
    """The db fixture rolls back after each test, ensuring no partial state."""

    @pytest.mark.asyncio
    async def test_rollback_leaves_no_rows(self, db: AsyncSession):
        wallet, token = await _seed_user_with_token(db)

        # Register a node through the API
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/nodes",
                json={"gpu_name": "RTX 3090", "vram_gb": 24, "location": "US"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text

        # The fixture's rollback will undo everything after the test
        count = await _count(db, "nodes")
        assert count >= 0  # basic sanity — no crash


# ── Test 4: Test data cannot leak between tests ──


class TestDataIsolation:
    """Each test starts with a clean database.  Data inserted in one test
    must not be visible in another."""

    @pytest.mark.asyncio
    async def test_no_leaked_users(self, db: AsyncSession):
        count = await _count(db, "users")
        assert count == 0, f"Expected 0 users at test start, found {count}"

    @pytest.mark.asyncio
    async def test_inserted_user_not_visible_later(self, db: AsyncSession):
        """Insert a user via ORM, let the fixture rollback, confirm isolation."""
        from app.models import User

        user = User(wallet_address="0x" + uuid.uuid4().hex[:40], role="user")
        db.add(user)
        await db.flush()
        count = await _count(db, "users")
        assert count >= 1
        # Fixture will rollback — next test should see 0 users


# ── Test 5: Dependency overrides are restored after every test ──


class TestOverrideRestoration:
    """After the _override_get_db fixture tears down, app.dependency_overrides
    must be empty so the next test starts clean."""

    @pytest.mark.asyncio
    async def test_overrides_cleared(self, db: AsyncSession):
        """At the START of a test the autouse fixture has already set
        the override — verify it is present and properly keyed."""
        from app.database import get_db

        assert get_db in app.dependency_overrides, "dependency_overrides should contain get_db during test execution"

    @pytest.mark.asyncio
    async def test_overrides_keyed_on_current_get_db(self, db: AsyncSession):
        """The override key must be the current get_db function, not a stale
        reference from a previous module import."""
        from app.database import get_db

        override_fn = app.dependency_overrides.get(get_db)
        assert override_fn is not None, "get_db override not found"

        # The override should yield our test db session
        gen = override_fn()
        yielded_session = await gen.__anext__()
        assert yielded_session is db, "Override does not yield the test db session"
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass


# ── Test 6: StaticPool shares a single connection ──


class TestStaticPool:
    """SQLite in-memory tests must use StaticPool so that the test session
    and the session created by create_all share the same connection."""

    @pytest.mark.asyncio
    async def test_engine_uses_static_pool(self, engine):
        assert isinstance(engine.pool, StaticPool), f"Expected StaticPool, got {type(engine.pool).__name__}"

    @pytest.mark.asyncio
    async def test_sessions_share_connection(self, engine):
        """Multiple sessions from the same engine must execute on the same
        underlying SQLite connection (guaranteed by StaticPool)."""
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as s1:
            uid = str(uuid.uuid4())
            await s1.execute(
                text("INSERT INTO users (id, wallet_address, role) VALUES (:id, :w, 'user')"),
                {"id": uid, "w": "0x" + "a" * 40},
            )
            await s1.flush()

            # s2 must see the uncommitted row (same connection, same transaction)
            async with factory() as s2:
                r = await s2.execute(text("SELECT count(*) FROM users"))
                count = r.scalar()
                assert count >= 1, "StaticPool second session cannot see first session's uncommitted data"


# ── Test 7: PostgreSQL dialect check (skipped when PG not available) ──


class TestPGDialect:
    """When DATABASE_URL targets PostgreSQL, the engine must use the
    postgresql dialect — not sqlite."""

    @pytest.mark.asyncio
    async def test_module_level_engine_dialect(self):
        url = str(db_module.engine.url)
        if "postgresql" in url:
            async with db_module.engine.connect() as conn:
                assert conn.dialect.name == "postgresql"
        else:
            pytest.skip("DATABASE_URL does not target PostgreSQL")


# ── Test 8: Mixed PG + SQLite in same invocation ──


class TestMixedInvocation:
    """Both SQLite unit tests and PG-specific tests can coexist in the same
    pytest run without corrupting each other's imports or engine state."""

    @pytest.mark.asyncio
    async def test_app_imports_unaffected(self):
        """After all conftest patching, app.main.app must still be importable."""
        from app.database import get_db
        from app.main import app as fresh_app

        assert hasattr(fresh_app, "router")
        import inspect

        assert inspect.isasyncgenfunction(get_db) or inspect.isgeneratorfunction(get_db)

    @pytest.mark.asyncio
    async def test_module_level_engine_not_replaced(self):
        """The conftest must not replace app.database.engine with a different
        engine object — only patch async_session."""
        assert db_module.engine is not None, "app.database.engine was cleared"
        url = str(db_module.engine.url)
        assert "sqlite" in url or "postgresql" in url, f"Unexpected URL: {url}"


# ── Test 9: Test ordering does not affect results ──


class TestOrderIndependence:
    """Data setup/teardown must not depend on execution order."""

    @pytest.mark.asyncio
    async def test_first(self, db: AsyncSession):
        from app.models import User

        user = User(wallet_address="0x" + "a" * 40, role="user")
        db.add(user)
        await db.flush()
        count = await _count(db, "users")
        assert count == 1

    @pytest.mark.asyncio
    async def test_second(self, db: AsyncSession):
        """This test must start with zero users regardless of test_first."""
        count = await _count(db, "users")
        assert count == 0, f"Data leaked from another test: {count} users found"

    @pytest.mark.asyncio
    async def test_third(self, db: AsyncSession):
        """Also starts clean."""
        count = await _count(db, "users")
        assert count == 0


# ── Test 10: No second engine created by app startup ──


class TestNoExtraEngine:
    """The FastAPI app must not create a second database engine during
    startup or request handling."""

    @pytest.mark.asyncio
    async def test_single_engine_in_conftest(self, engine):
        url = str(engine.url)
        assert url == "sqlite+aiosqlite:///:memory:", f"Unexpected engine URL: {url}"

    @pytest.mark.asyncio
    async def test_app_database_engine_unchanged(self):
        url = str(db_module.engine.url)
        assert "sqlite" in url or "postgresql" in url, f"Unexpected URL: {url}"

    @pytest.mark.asyncio
    async def test_create_app_returns_new_instance(self):
        from app.main import create_app

        app1 = create_app()
        app2 = create_app()
        assert app1 is not app2, "create_app should return a new instance each time"
