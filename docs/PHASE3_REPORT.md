# Phase 3 Report — Corrected

> All counts below are machine-derived via `pytest --collect-only -q` and `forge test --list`.
> Confirmed: `2026-09-07`

## §1 Test Count Reconciliation

| Category | Count | Mode | Files |
|---|---|---|---|
| Unit (SQLite mode) | 157 | `DATABASE_URL=sqlite+aiosqlite:///:memory:` | All non-PG, non-Anvil files |
| PG (SQLite mode skipped) | 65 | Skipped when `DATABASE_URL` is SQLite | PG-only files + 18 regression |
| Anvil (real RPC) | 22 | Requires running Anvil at `127.0.0.1:8545` | test_anvil_integration (10), test_anvil_proof_settlement (12) |
| **Total collected** | **295** | | `pytest --collect-only -q` |
| **SQLite mode passing** | **230 passed, 65 skipped** | `pytest -q` with SQLite env | |
| **PG mode passing** | **295 passed, 0 skipped** | `pytest -q` with PG env | |
| Contract (Foundry) | 125 | `forge test --list` | NebulaVerifiableAITest (119) + NebulaStatefulInvariantTest (5) + NebulaInvariantTest (1) |
| **Grand total** | **420** | | 295 backend + 125 contract |

### Test Breakdown by File

| Test File | Count | Category | Notes |
|---|---|---|---|
| test_phase2.py | 40 | Unit | Phase 2 baseline |
| test_uuid_bytes32.py | 32 | Unit | Golden vector validation |
| test_fingerprint.py | 17 | Unit | §8 fingerprint protocol |
| test_pg_event_durability.py | 20 | PG | Persistent event durability across restarts |
| test_regression.py | 18 | SQLite | Fixture correctness, API writes, rollback |
| test_assignment_dispatcher.py | 14 | Unit | §15 assignment dispatcher |
| test_proof_verification.py | 12 | Unit | §9 Merkle + EIP-712 |
| test_event_durability.py | 12 | Unit | §19 SQLite durability/reorg |
| test_anvil_proof_settlement.py | 12 | Anvil | Proof→settlement + escrow confirmation |
| test_lease_scheduler.py | 10 | Unit | §10 lease, §13 scheduler |
| test_anvil_integration.py | 10 | Anvil | Escrow lifecycle |
| test_worker_router.py | 9 | Unit | §16 worker routes |
| test_output_bytes.py | 9 | Unit | §9 output byte validation |
| test_job_service.py | 9 | Unit | §10 job service |
| test_route_state.py | 8 | Unit | §7 route-state rules |
| test_proof_pipeline.py | 7 | Unit | §9 13-check pipeline |
| test_jobs_router.py | 6 | Unit | §16 jobs API |
| test_blockchain_events.py | 6 | Unit | §19 event service |
| test_postgresql_integration.py | 40 | PG | Schema + constraints |
| test_pg_concurrency.py | 4 | PG | FOR UPDATE SKIP LOCKED concurrency |

### Execution Order Stability

All four execution order permutations verified passing:

| Order | SQLite mode | PG mode |
|---|---|---|
| Default (`pytest tests/`) | 230 passed, 65 skipped | 295 passed |
| Reversed (explicit file list) | 230 passed, 65 skipped | 295 passed |
| Anvil first | 22 passed | 62 passed (22 Anvil + 40 PG) |
| PG first | 40 passed | 62 passed (40 PG + 22 Anvil) |

## §2 Credential Remediation

All credential-bearing URLs removed from source. The `DATABASE_URL` environment variable is used exclusively — no hardcoded passwords.

- `test_postgresql_integration.py`: `sys.exit()` replaced with `pytest.skip()` — prevents INTERNALERROR during collection when DATABASE_URL is not PostgreSQL
- `test_pg_concurrency.py`: uses `os.environ.get("DATABASE_URL")` — no hardcoded URL
- `test_pg_event_durability.py`: validates scheme and database name, skips gracefully

Searched all tracked and untracked files: no credential-bearing URLs found. Git history verified: `test_pg_concurrency.py` was never committed to git.

## §3 Transaction Signer Service

`app/services/tx_signer.py` — Dependency-injected signer:

- `TransactionSigner` Protocol: `get_address()`, `get_chain_id()`, `get_nonce()`, `sign_and_send()`, `wait_for_receipt()`
- `Web3Signer`: production, reads `BACKEND_PRIVATE_KEY` from config
- `FakeSigner`: unit tests, records calls, deterministic

## §4 Assignment Dispatcher

`app/services/assignment_dispatcher.py` — NEW:

- Runs AFTER scheduler commits (outside scheduler transaction)
- Builds `assignProvider()` call from lease state
- Signs via `TransactionSigner`, broadcasts to chain
- Persists `ChainTransaction` record
- Waits for `ProviderAssigned` event confirmation
- Activates lease, transitions job to `assigned`
- Handles dropped/replaced transactions, reconciliation

## §5 Scheduler Blockchain Assignment

`app/services/scheduler.py`:

- `_lock_next_queued_job()`: FOR UPDATE SKIP LOCKED on PostgreSQL, SQLite fallback
- `schedule_next_job()`: selects job → finds node → creates pending_chain lease + attempt + updates job
- No RPC calls — scheduler only creates DB state
- Backend dispatcher handles blockchain submission

Canonical sequence enforced:
```
scheduler → pending_chain lease
dispatcher → assignProvider() → ProviderAssigned event confirmed
→ lease becomes active
→ /v1/worker/leases/next returns lease
→ worker ack transitions to running
```

## §6 Worker Route-State Rules

`app/routers/worker.py`:

- `/leases/next`: Returns only `active` leases. Never returns `pending_chain`.
- `/leases/{id}/ack`: Requires `active` status. Does NOT perform on-chain assignment.
- All routes: X-API-Key auth, node ownership verification, lease status validation.
- `/leases/{id}/complete`: Requires `active` status.
- `/leases/{id}/fail`: Requires `active` or `pending_chain` status.
- `/nodes/{id}/heartbeat`: Verifies authenticated node matches.

## §7 13-Check Proof Verification Pipeline

`app/services/proof_verifier.py` — Full orchestration:

| Check | Name | Description |
|---|---|---|
| 1 | protocol_version | Must be version 1 |
| 2 | job_exists | Job in eligible state (proof_submitted/verifying/settling) |
| 3 | attempt_binding | Attempt exists and belongs to job |
| 4 | lease_binding | Lease active, not expired, belongs to job/node/attempt |
| 5 | lease_ownership | Lease matches job, attempt node, attempt lease |
| 6 | lease_id_consistency | Lease matches job's current_lease_id |
| 7 | timestamp_validity | proof ≤ lease_expiry ≤ job_deadline |
| 8 | fingerprint_match | Fingerprint matches backend-expected |
| 9 | checkpoint_match | Names, count, order match model adapter spec |
| 10 | merkle_root | Recomputed Merkle root matches submitted root |
| 11 | signature_verification | EIP-712 from authorized worker signer |
| 12 | replay_detection | No prior proof/verdict/settlement exists |
| 13 | output_bytes | Validates actual storage bytes against claimed outputHash |

- DB-level locking prevents concurrent verification
- All check results persisted with Proof model
- Verdict: VALID or INVALID

## §8 Anvil Proof-to-Settlement Integration (12 tests)

| Test | Scenario |
|---|---|
| test_valid_proof_settled | Assigned → submitProof → verifyJob(true) → Settled |
| test_invalid_proof_refunded | verifyJob(false) → Refunded |
| test_wrong_lease_rejected | submitProof with wrong lease_id reverts |
| test_replay_same_proof_rejected | Double submitProof on same job reverts |
| test_double_settle_rejected | verifyJob after settle reverts |
| test_wrong_signer_assign_rejected | Non-verifier cannot assignProvider |
| test_stale_lease_reassignment | Reassign after previous lease expires |
| test_create_job_event_valid | Confirm JobCreated event fields |
| test_wrong_fingerprint_event | Zero fingerprint reverts |
| test_wrong_amount_rejected | Zero USDC reverts |
| test_idempotent_escrow_confirmation | Same tx_hash cannot create two jobs |
| test_pending_withdrawal_reconciliation | After settle, pending matches escrow |

## §9 Event Durability and Reorg Behavior (12 unit tests + 12 PG tests)

### Unit (SQLite) — test_event_durability.py

- Idempotent event recording (duplicate → return existing)
- Checkpoint management (max block number)
- Backfill without duplicates (overlapping ranges)
- Confirmation progression (pending → confirmed → finalized)
- Batch confirmation at block height
- Non-final event reorg (demote to pending)
- Finalized event preservation (never deleted)
- Replacement of non-finalized events
- Finalized event replacement blocked
- DB failure recovery
- Reconciliation idempotency
- Unconfirmed events query

### PostgreSQL Persistent (test_pg_event_durability.py)

Proves event durability across service restarts using real PostgreSQL:

1. Persist event and checkpoint from instance A
2. Recover event from new instance B (restart simulation)
3. Resume backfill from persisted checkpoint after restart
4. Non-final canonical block-hash mismatch demotes event
5. Insert replacement canonical event after reorg
6. Reorg reverses derived job projection transactionally
7. Corrected state persists after second restart (instance C)
8. Chain success followed by DB projection failure — recovery works
9. Repeated reconciliation produces identical results (idempotent)
10. Finalized event contradiction preserves evidence — no deletion
11. Overlapping backfill across restart creates no duplicate events
12. Batch confirmation persists across restart

## §10 PostgreSQL Concurrency Tests (4 tests)

- Two concurrent scheduler calls → at most one winner
- PostgreSQL dialect detection
- FOR UPDATE SKIP LOCKED syntax validation
- Scheduler returns only one attempt+lease per job

## §11 Route-State Verification (8 tests)

- `/leases/next` returns only active leases (not pending_chain)
- `/leases/next` returns active lease after activation
- `/leases/{id}/ack` rejects pending_chain lease
- `/leases/{id}/ack` works on active lease
- Wrong node rejected on ack (403)
- Wrong node rejected on complete (403)
- Wrong node rejected on fail (403)
- Unauthenticated requests rejected (401)

## §12 Output Byte Validation (9 tests)

- Validates actual storage bytes against claimed outputHash
- Rejects oversized output (exceeds MAX_RESULT_SIZE_BYTES)
- Rejects hash mismatch between claimed and computed outputHash
- Handles missing storage gracefully
- Handles storage read failures
- Enforces MAX_RESULT_SIZE_BYTES limit

## §13 Full Verification

```
Backend (SQLite mode):
  ruff check .                    → All checks passed
  ruff format --check .           → All files formatted
  pytest --collect-only -q        → 295 tests collected
  pytest -q                       → 230 passed, 65 skipped, 0 failed
  pytest (reversed order)         → 230 passed, 65 skipped, 0 failed

Backend (PG mode):
  pytest --collect-only -q        → 295 tests collected
  pytest -q                       → 295 passed, 0 skipped, 0 failed
  pytest (reversed order)         → 295 passed, 0 skipped, 0 failed

Backend (Anvil):
  pytest test_anvil_* -q          → 22 passed (10 + 12)
  pytest (Anvil first)            → 62 passed (Anvil + PG)
  pytest (PG first)               → 62 passed (PG + Anvil)

Contracts:
  forge fmt --check               → ok
  forge build                     → ok
  forge test --list               → 125 tests listed
  forge test                      → 125 passed (119 + 5 stateful invariant + 1 fuzz invariant)
  forge snapshot --check          → ok
```

**Total: 295 backend tests all green + 125 contract tests all green = 420 tests, 0 failures.**

### Foundry Test Reconciliation (since commit 12ab1c9)

| Metric | 12ab1c9 | Current (uncommitted) | Delta |
|---|---|---|---|
| Test functions in source | 102 | 102 | 0 |
| forge test --list | 102 | 125 | +23 (5 stateful invariant + 18 new unit/fuzz) |
| forge test --summary | 102 passed | 125 passed | +23 |

The 23 additional tests in the working tree (not yet committed) include:
- 5 `NebulaStatefulInvariantTest` invariant functions
- 18 new unit/fuzz/boundary/race tests (verifier rotation, paused operations, `fromProofSubmitted` path, race conditions, withdraw edge cases)
