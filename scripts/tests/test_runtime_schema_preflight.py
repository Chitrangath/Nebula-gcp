"""Read-only runtime compatibility checks before live jobs or transactions."""

import sqlite3
from pathlib import Path

import pytest
import uvloop
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]


def test_stale_database_requires_reviewed_migration_without_changing_it(tmp_path: Path) -> None:
    from scripts.runtime_schema_preflight import require_current_schema

    database = tmp_path / "stale.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('0008_proof_verification_claims')")

    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        uvloop.run(require_current_schema(f"sqlite+aiosqlite:///{database}"))

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == [
            ("0008_proof_verification_claims",)
        ]


def test_database_at_code_migration_heads_passes_without_changes(tmp_path: Path) -> None:
    from scripts.runtime_schema_preflight import require_current_schema

    heads = ScriptDirectory(str(ROOT / "backend/alembic")).get_heads()
    database = tmp_path / "current.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL)")
        connection.executemany("INSERT INTO alembic_version VALUES (?)", [(head,) for head in heads])

    assert uvloop.run(require_current_schema(f"sqlite+aiosqlite:///{database}")) is None

    with sqlite3.connect(database) as connection:
        assert {row[0] for row in connection.execute("SELECT version_num FROM alembic_version")} == set(heads)


def test_missing_version_table_requires_migration_without_creating_it(tmp_path: Path) -> None:
    from scripts.runtime_schema_preflight import require_current_schema

    database = tmp_path / "unversioned.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE existing_data (value INTEGER)")

    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        uvloop.run(require_current_schema(f"sqlite+aiosqlite:///{database}"))

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall() == [
            ("existing_data",)
        ]


def test_connection_errors_never_expose_database_credentials() -> None:
    from scripts.runtime_schema_preflight import require_current_schema

    url = "invalid-driver://private-user:private-password@private-host/database?token=private-query"

    with pytest.raises(RuntimeError, match="check protected DATABASE_URL") as caught:
        uvloop.run(require_current_schema(url))

    for secret in (url, "private-user", "private-password", "private-host", "private-query"):
        assert secret not in str(caught.value)
    assert caught.value.__suppress_context__ is True
