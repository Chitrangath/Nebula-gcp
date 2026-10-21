"""Conftest for backend tests.

Uses SQLite for basic constraint testing when PostgreSQL is unavailable.

SQLite :memory: databases are per-connection.  Fix (three parts):
  1. StaticPool — all sessions share one connection.
  2. FastAPI dependency_overrides — HTTP handlers receive the test's db
     session directly, guaranteeing transaction visibility.
  3. connect_args check_same_thread=False — required for async SQLite.

The _override_get_db autouse fixture imports get_db at setup time (not
module level) so it survives any module reloads that other test modules
might trigger.  No test module should ever mutate sys.modules.
"""

import asyncio
import os
import sys
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

# Set env before importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing-only-32chars")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest_asyncio
import uvloop
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.database as db_module
from app.main import app
from app.services.storage import InMemoryStorage


def pytest_asyncio_loop_factories() -> dict[str, Callable[[], asyncio.AbstractEventLoop]]:
    """Use uvloop; the platform selector loop can deadlock aiosqlite teardown."""
    return {"uvloop": uvloop.new_event_loop}


@pytest_asyncio.fixture
async def engine():
    import app.models  # noqa: F401 — registers all models with Base
    from app.database import Base

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Patch app.database to use the test engine
    original_factory = db_module.async_session
    db_module.async_session = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)

    yield eng

    db_module.async_session = original_factory
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine):
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(autouse=True)
async def _override_get_db(db: AsyncSession):
    """Override FastAPI's get_db dependency so HTTP handlers use the test session.

    The import is done at setup time (not module level) so it resolves the
    current ``get_db`` even if another test module reimports ``app.database``.

    This guarantees:
      - API writes are visible through the injected test session.
      - Routers and services use the same request-scoped session.
      - No hidden session creation in the request path.
    """
    from app.database import get_db

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    app.state.storage = InMemoryStorage()
    yield
    app.dependency_overrides.clear()


async def seed_authed_user(db: AsyncSession) -> tuple[uuid.UUID, str]:
    """Create a user + auth session, return (user_id, valid_jwt_token)."""
    from app.models import AuthSession, User
    from app.services.auth_service import create_access_token, sha256_hex

    user_id = uuid.uuid4()
    wallet = "0x" + uuid.uuid4().hex
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
    return user_id, token
