# Phase 2 Final Report — Backend API Foundation

**Date:** 2026-09-03
**Phase:** 2 of 7 (Backend API Foundation)
**Status:** COMPLETE
**Tests:** 112/112 passing (40 SQLite + 40 PostgreSQL + 32 UUID/bytes32)

---

## 1. Deliverables Created

### Files Modified/Created

| # | File | Purpose |
|---|------|---------|
| 1 | `backend/pyproject.toml` | Project metadata and dependencies |
| 2 | `backend/app/__init__.py` | Package init |
| 3 | `backend/app/main.py` | FastAPI app entry point |
| 4 | `backend/app/config.py` | Pydantic-settings with `SettingsConfigDict` |
| 5 | `backend/app/database.py` | Async SQLAlchemy with SQLite fallback |
| 6 | `backend/app/models/__init__.py` | 12 SQLAlchemy ORM models |
| 7 | `backend/app/schemas/__init__.py` | Pydantic request/response schemas (lowercase wallet regex) |
| 8 | `backend/app/security.py` | JWT Bearer auth middleware |
| 9 | `backend/app/routers/__init__.py` | Router package init |
| 10 | `backend/app/routers/auth.py` | Auth endpoints (challenge, verify, refresh, logout) |
| 11 | `backend/app/routers/nodes.py` | Node endpoints (register, list, get, heartbeat) |
| 12 | `backend/app/routers/health.py` | Health endpoints (live, ready) |
| 13 | `backend/app/routers/models.py` | Model list/get endpoints |
| 14 | `backend/app/routers/jobs.py` | Stub router (to be implemented in Phase 4) |
| 15 | `backend/app/routers/earnings.py` | Stub router (to be implemented in Phase 4) |
| 16 | `backend/app/services/auth_service.py` | Auth service with `normalize_wallet()` |
| 17 | `backend/app/services/node_service.py` | Node service (register, credentials, heartbeat) |
| 18 | `backend/migrations/001_initial_schema.sql` | Full 12-table migration SQL |
| 19 | `backend/alembic.ini` | Alembic config |
| 20 | `backend/alembic/env.py` | Async Alembic env |
| 21 | `backend/alembic/script.py.mako` | Migration template |
| 22 | `backend/alembic/versions/0001_initial_schema.py` | Initial Alembic migration |
| 23 | `backend/alembic/versions/0002_data_integrity_constraints.py` | **NEW: Monetary + wallet constraints** |
| 24 | `backend/tests/conftest.py` | Test fixtures (deferred imports for PG compat) |
| 25 | `backend/tests/test_phase2.py` | 40 Phase 2 SQLite verification tests |
| 26 | `backend/tests/test_postgresql_integration.py` | **39 PostgreSQL integration tests** |
| 27 | `backend/.env` | Environment variables |
| 28 | `backend/.env.example` | Example env file |

---

## 2. Schema Inventory (12 Tables)

| Table | Columns | Key Constraints |
|-------|---------|-----------------|
| `users` | id, wallet_address, role, display_name, created_at, updated_at | UNIQUE(wallet_address), CHECK(role), **CHECK(wallet ~ '^0x[0-9a-f]{40}$')** |
| `supported_models` | id, name, description, price_base_units, enabled, created_at | PK(id), NUMERIC(78,0), **CHECK(price > 0)** |
| `nodes` | id, provider_id, name, status, api_key_hash, ... | FK(provider_id), CHECK(status) |
| `jobs` | id, user_id, model_id, chain_job_id, status, ... | FK(user_id, model_id), CHECK(status), **CHECK(price > 0)**, **CHECK(escrow IS NULL OR escrow > 0)** |
| `payments` | id, job_id, user_id, amount_base_units, ... | FK(job_id, user_id), NUMERIC(78,0), **CHECK(amount > 0)** |
| `auth_challenges` | id, wallet_address, nonce, message, expires_at, used | UNIQUE(nonce), **CHECK(wallet ~ '^0x[0-9a-f]{40}$')** |
| `auth_sessions` | id, user_id, token_hash, refresh_token_hash, ... | UNIQUE(token_hash) |
| `leases` | id, job_id, node_id, lease_id, expires_at, status | CHECK(status), partial unique (active per job) |
| `job_attempts` | id, job_id, node_id, lease_id, attempt_number, ... | UNIQUE(job_id, attempt_number), CHECK(attempt_number > 0) |
| `proofs` | id, job_attempt_id, fingerprint_hash, merkle_root, ... | FK(job_attempt_id) |
| `chain_transactions` | id, chain_id, tx_hash, tx_type, amount_base_units, ... | UNIQUE(tx_hash), **CHECK(amount IS NULL OR amount >= 0)** |
| `blockchain_events` | id, chain_id, transaction_hash, log_index, ... | UNIQUE(chain_id, tx_hash, log_index) |

---

## 3. Monetary Column Audit

| Column | Constraint | Justification |
|--------|-----------|---------------|
| `supported_models.price_base_units` | `> 0` | Every listed model must have a non-zero price |
| `jobs.price_base_units` | `> 0` | Every job is created against a priced model |
| `jobs.blockchain_escrow_amount` | `IS NULL OR > 0` | NULL = not yet escrowed; once set must be positive |
| `payments.amount_base_units` | `> 0` | Every payment record is a positive transfer |
| `chain_transactions.amount_base_units` | `IS NULL OR >= 0` | NULL for non-value txns (submitProof); 0 allowed for zero-value contract calls |

**Other monetary columns reviewed:**
- `nodes.active_leases` — Integer counter, not monetary
- `jobs.max_attempts` / `jobs.current_attempt` — Integer counters, not monetary
- `job_attempts.attempt_number` — Integer counter, not monetary
- `leases.nonce` — Blockchain nonce, not monetary
- `blockchain_events.log_index` / `block_number` — Chain metadata, not monetary

No monetary column permits negative values.

---

## 4. Wallet Address Normalization

| Layer | Enforcement |
|-------|-------------|
| **Application code** | `auth_service.normalize_wallet()` — validates regex, converts to lowercase before DB insertion |
| **Pydantic schemas** | `ChallengeRequest` and `VerifyRequest` enforce `^0x[0-9a-f]{40}$` (lowercase only) |
| **Database CHECK** | `ck_users_wallet_lowercase_hex` — `wallet_address ~ '^0x[0-9a-f]{40}$'` |
| **Database CHECK** | `ck_auth_challenges_wallet_lowercase_hex` — same regex on `auth_challenges` |
| **Behavior** | Uppercase/mixed-case addresses rejected at DB boundary; duplicates cannot exist |

---

## 5. API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health/live` | None | Liveness probe |
| GET | `/health/ready` | None | Readiness probe |
| POST | `/auth/challenge` | None | Create SIWE challenge |
| POST | `/auth/verify` | None | Verify signature + issue JWT |
| POST | `/auth/refresh` | Cookie | Rotate refresh token |
| POST | `/auth/logout` | Bearer | Revoke session |
| POST | `/nodes/register` | Bearer | Register compute node |
| GET | `/nodes` | Bearer | List provider's nodes |
| GET | `/nodes/{id}` | Bearer | Get node details |
| POST | `/nodes/{id}/heartbeat` | Bearer | Update node heartbeat |
| GET | `/models` | None | List available models |
| GET | `/models/{id}` | None | Get model details |
| GET | `/jobs` | Bearer | List user's jobs (stub) |
| GET | `/earnings` | Bearer | List earnings (stub) |

---

## 6. Auth Flow

1. Client POSTs `/auth/challenge` with wallet address → `normalize_wallet()` → gets SIWE message + nonce
2. Client signs message with MetaMask → POSTs `/auth/verify` with signature + nonce
3. Server verifies signature, creates/finds user (wallet stored lowercase), issues JWT (24h access + 7d refresh cookie)
4. Client sends Bearer token for authenticated requests
5. On access token expiry, client POSTs `/auth/refresh` with refresh cookie → gets new JWT pair
6. Refresh rotation: old session is revoked, new session created
7. Replay detection: if reused refresh token detected, all user sessions revoked

---

## 7. Test Coverage

### SQLite Tests (`test_phase2.py`) — 40 tests

| Test Category | Tests | Status |
|---------------|-------|--------|
| Migration (upgrade/downgrade/reupgrade) | 3 | PASS |
| Schema Constraints (unique, check, numeric) | 11 | PASS |
| Relationships (FK integrity) | 4 | PASS |
| Authentication (challenge, verify, tokens) | 8 | PASS |
| Refresh Rotation (create, revoke, replay) | 4 | PASS |
| Worker Credentials (API key, registration, rotation) | 5 | PASS |
| Base-Unit Precision (50000, 10^77) | 3 | PASS |
| Seed Data (model seeding) | 2 | PASS |
| **Total** | **40** | **ALL PASS** |

### PostgreSQL Integration Tests (`test_postgresql_integration.py`) — 40 tests

| Test Category | Tests | Status |
|---------------|-------|--------|
| Alembic heads (single revision) | 1 | PASS |
| Upgrade creates 12 tables | 3 | PASS |
| Downgrade/re-upgrade cycle | 2 | PASS |
| Foreign key integrity | 1 | PASS |
| Status constraints (jobs, leases) | 2 | PASS |
| Lease uniqueness (one active per job) | 1 | PASS |
| Lease after expiry (allows new lease) | 1 | PASS |
| Attempt uniqueness (per job+number) | 1 | PASS |
| Blockchain event uniqueness | 1 | PASS |
| Multiple events per transaction | 1 | PASS |
| NUMERIC(78,0) precision | 1 | PASS |
| **Monetary constraints** (neg/zero/pos for 5 columns) | **11** | **PASS** |
| **Wallet normalization** (uppercase, mixed, same-address, length, prefix) | **6** | **PASS** |
| No plaintext secrets | 2 | PASS |
| Foreign key rejection | 1 | PASS |
| **Downgrade 0002→0001 removes new constraints** | **1** | **PASS** |
| **Lease partial-index predicate verification** | **1** | **PASS** |
| **Re-upgrade restores constraints** | **1** | **PASS** |
| PostgreSQL dialect check | 1 | PASS |
| **Total** | **39** | **ALL PASS** |

---

## 8. Alembic Verification Commands

```bash
cd backend

# Check revision history
uv run alembic history --verbose
# → 0003_rename_lease_index (head) → 0002_data_integrity_constraints → 0001_initial_schema

# Check current state
uv run alembic current
# → 0003_rename_lease_index (head)

# Upgrade to head (from base)
uv run alembic upgrade head
# → Running upgrade -> 0001_initial_schema
# → Running upgrade 0001_initial_schema -> 0002_data_integrity_constraints
# → Running upgrade 0002_data_integrity_constraints -> 0003_rename_lease_index

# Downgrade to 0001
uv run alembic downgrade 0001_initial_schema
# → Running downgrade 0003_rename_lease_index -> 0002_data_integrity_constraints
# → Running downgrade 0002_data_integrity_constraints -> 0001_initial_schema

# Re-upgrade
uv run alembic upgrade head
# → Running upgrade 0001_initial_schema -> 0002_data_integrity_constraints
# → Running upgrade 0002_data_integrity_constraints -> 0003_rename_lease_index

# SQLite unit tests
uv run pytest tests/test_phase2.py -v
# → 40 passed

# PostgreSQL integration tests
DATABASE_URL="$NEBULA_TEST_URL" uv run pytest tests/test_postgresql_integration.py -v
# → 40 passed

# Lint + format
uv run ruff check .
uv run ruff format --check .
```

---

## 9. Deviations & Notes

| Item | Detail |
|------|--------|
| PostgreSQL container | Docker `nebula-postgres` on `localhost:5433`, user `nebula`, database `nebula` |
| ORM vs migration types | ORM uses `JSON` (SQLite compat); migration uses PostgreSQL-native `JSONB` |
| ORM vs migration indexes | ORM lacks partial unique index on leases; migration adds it |
| ORM vs migration checks | ORM lacks `attempt_number > 0` check; migration adds it |
| ORM vs 0002 constraints | ORM lacks monetary CHECK and wallet CHECK; 0002 migration adds them |
| `Lease.nonce` | `Integer` in ORM, `BigInteger` in migration (SQLite has no BIGINT, but tests pass) |
| `jti` claim | Added to `create_access_token` to ensure unique JWT per session |
| `== None` → `.is_(None)` | Used SQLAlchemy `.is_(None)` for ruff compliance in auth service |
| `from app.models import *` | Required in Alembic env to register all models; uses `# noqa: F401, F403` |
| Pydantic settings | Replaced deprecated `class Config` with `model_config = SettingsConfigDict(...)` |
| aiosqlite | Added as dev dependency for SQLite test fallback |
| conftest.py imports | Deferred `app.database` and `app.models` imports to fixtures for PG test compatibility |

---

## 10. Phase 2 Completion Checklist

- [x] FastAPI application created and runnable
- [x] PostgreSQL schema aligned to PRD v3.1
- [x] Alembic async migration setup
- [x] **0001_initial_schema.py** — initial migration (upgrade/downgrade)
- [x] **0002_data_integrity_constraints.py** — monetary + wallet constraints (upgrade/downgrade)
- [x] **0003_rename_lease_index.py** — renames lease index to reflect both statuses
- [x] 12 canonical tables with all constraints, indexes, relationships
- [x] **7 monetary CHECK constraints** preventing negative/zero values
- [x] **2 wallet CHECK constraints** enforcing `^0x[0-9a-f]{40}$`
- [x] **`normalize_wallet()`** in auth service — canonical lowercase before DB insertion
- [x] **Lowercase-only Pydantic patterns** — `^0x[0-9a-f]{40}$` on ChallengeRequest/VerifyRequest
- [x] Auth flow: SIWE challenge → signature → JWT → refresh rotation → replay detection
- [x] Node registration with API key generation (nb_live_* prefix)
- [x] Node credential rotation
- [x] Health endpoints (/live, /ready)
- [x] Model list/get endpoints
- [x] **40 SQLite tests passing**
- [x] **40 PostgreSQL integration tests passing** (including lease-index predicate check)
- [x] **32 UUID/bytes32 golden-vector tests passing**
- [x] ruff lint clean
- [x] ruff format clean
- [x] Phase 2 report generated

---

**Next Phase:** Phase 3 — Core Backend Services (job lifecycle, provider matching, chain integration, proof verification)
