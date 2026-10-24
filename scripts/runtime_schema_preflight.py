"""Reject stale runtime databases before any live provisioning or transactions."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]


async def _database_heads(database_url: str) -> tuple[str, ...]:
    engine = create_async_engine(database_url, poolclass=NullPool, hide_parameters=True)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(lambda conn: MigrationContext.configure(conn).get_current_heads())
    finally:
        await engine.dispose()


async def require_current_schema(database_url: str) -> None:
    """Require the intended database to match this checkout's migration heads, without writes."""
    try:
        expected_heads = set(ScriptDirectory(str(ROOT / "backend/alembic")).get_heads())
        if not expected_heads:
            raise ValueError("missing migration heads")
    except Exception:  # noqa: BLE001 - expose only an actionable repository error
        raise RuntimeError("Cannot read runtime migration requirements; review backend/alembic before live writes.") from None
    try:
        actual_heads = set(await asyncio.wait_for(_database_heads(database_url), timeout=15))
    except Exception:  # noqa: BLE001 - DBAPI errors may include credentials or connection URLs
        raise RuntimeError(
            "Database schema preflight could not read migration state; check protected DATABASE_URL "
            "connectivity and retry before any live writes."
        ) from None
    if actual_heads != expected_heads:
        raise RuntimeError(
            "Database schema is not current. From backend/, review and run '.venv/bin/alembic upgrade head' "
            "with the intended protected DATABASE_URL, then retry. No migrations were applied by this preflight."
        )
