# Nebula AI Cloud Phase 3 Integration Closure Report

Date: 2026-09-23
Verified commit: `726e6d59f3e81943f7a8eea75a61b801e4af2ee5` plus section 28
Target: local PostgreSQL `nebula_test` and disposable Anvil chains
Verdict: **PASS — local Phase 3 Integration Closure only**

## 1. Scope and canonical references

This audit used `AGENTS.md`, `CONTEXT.md`, PRD v3.1, the development plan,
Phase 2/3 reports, current contracts/artifacts, migrations, backend runtime and
tests, and the protocol worker. Current code and PRD v3.1 override stale report
interfaces. No Phase 4/5 work, deployment, commit, or push occurred.

## 2. Original disconnected runtime handoffs

Escrow confirmation, scheduling, chain assignment, worker completion, proof
verification, settlement, events, reconciliation, and final API projection
originally existed as partly independent slices. BE-001 later made upload
authoritative, leaving the old JSON E2E client stale.

## 3. Implemented runtime connection

```text
HTTP multipart upload -> PostgreSQL -> scheduler -> assignment dispatcher
-> Anvil contract -> protocol worker -> real ProofVerifier
-> submitProof/verifyJob -> settlement/refund -> event reconciliation
-> final public API response
```

The journey uses real uploaded bytes, server-derived hash/key/price/fingerprint,
MockUSDC/current Nebula deployments, signed Anvil transactions, real runners,
the full proof envelope, chain events, and final API. It does not use fake chain
responses, direct status shortcuts, handwritten ABI, or mocked verifier success.

## 4. Files created and modified

The historical closure added migrations `0004`–`0008`, runtime runners,
transaction outbox/nonce coordination, receipt validation, retry/settlement,
event reconciliation, generated artifacts, protocol worker, and tests. This
final verification changes only the five files listed in section 28.

## 5. Canonical ABI, bytecode, and compiler

Canonical source: `contracts/out/NebulaVerifiableAI.sol/NebulaVerifiableAI.json`.
Artifact sync passed.

```text
ABI SHA-256              57a205796f5ea3e9189e281af31dcdc337386075f1ae8060a0d34fe3c5aaf0e9
Runtime SHA-256          54b4029baa8f1487adda2c3f7a676b54524ec8a591b61f843e63d349aa58faef
Runtime Keccak-256       0xad122086d9d75b65eb9a6331a798f7c0ea54ea580ec22bf81fe7272359850125
Initcode/runtime size    5,789 / 5,460 bytes
EIP-170 runtime margin   19,116 bytes
Compiler                 0.8.20+commit.a1b79de6
Optimizer/viaIR/EVM      200 runs / true / shanghai
```

## 6. ABI compatibility

Six ABI/artifact tests cover types/order, returns, events/indexing, custom
errors, tuple decoding, and `JobState` values 0–5.

| Function | Selector | Return |
|---|---|---|
| `createJob(bytes32,bytes32)` | `0x57251cc4` | `bytes32` |
| `assignProvider(bytes32,address,bytes32,uint64)` | `0x4e583fbf` | none |
| `submitProof(bytes32,bytes32,bytes32,bytes32)` | `0x3521e00d` | none |
| `verifyJob(bytes32,bool)` | `0xd3164c32` | none |
| `requestTimeoutRefund(bytes32)` | `0xc2a080b9` | none |
| `withdraw()` | `0x3ccfd60b` | none |
| `getJob(bytes32)` | `0xf729cf0d` | 12-field tuple |
| `getPendingWithdrawal(address)` | `0x7ee8b2f8` | `uint256` |

## 7. Database and migration status

Python 3.12.14 ran from `backend/.venv`. Docker 29.7.2 reported
`nebula-postgres` healthy on local port 5433; `pg_isready` succeeded. Every
destructive launcher asserted the `nebula_test` suffix without printing its URL.
Alembic head/current is `0008_proof_verification_claims`. The test schema has 15
application tables plus `alembic_version`. The development database was queried
read-only and remains at its pre-existing `0003`; no test targeted it.

The 64 PostgreSQL tests cover financial/wallet constraints, live-lease partial
uniqueness, attempt/proof/event uniqueness, idempotent intents, concurrent
schedulers/dispatchers/verifiers, durable recovery, and duplicate ingestion.

## 8. Runtime runner architecture

Bounded receipt, assignment, settlement, event, and reconciliation runners use
persist-before-broadcast intents and chain-instance-scoped nonce coordination.
Network calls occur outside long-lived row locks. Work and proof claims are
restartable and idempotent.

## 9. Public API changes

`POST /v1/jobs` accepts a bounded multipart upload and derives authoritative
price/hash/private storage key/fingerprint. Escrow confirmation accepts only `tx_hash`
and validates chain, contract, status, confirmations, sender, event, job,
fingerprint and amount. Worker result metadata cannot overwrite input metadata.
Final job/result routes remain authenticated and do not expose secrets/traces.

## 10. Minimal protocol worker

The E2E worker polls/acknowledges active leases, downloads/verifies exact bytes,
runs the fixture adapter, builds ordered Merkle evidence, signs full EIP-712
with a node signer separate from payout identity, uploads and completes. This is
protocol evidence, not real GPU inference.

## 11. Exact golden E2E sequence

Each journey performs upload, escrow/confirmation, scheduling, concurrent
dispatch, confirmed assignment, worker heartbeat/poll/ack/execute/upload/
complete, proof verification, settlement/refund, event restart/reconciliation,
final API/result assertions, pending-withdrawal verification and withdrawal.

## 12. Consecutive E2E results

Both runs used the same secret-safe launcher from the repository root (the
launcher reads `backend/.env`, rewrites only the database name to the isolated
`nebula_test` database, validates that suffix, and never prints the URL):

```text
set -a; source backend/.env; set +a; DATABASE_URL="${DATABASE_URL%/*}/nebula_test" backend/.venv/bin/pytest -q backend/tests/test_integration_closure_e2e.py
```

| Run | Collected | Passed | Failed | Errors | Skipped | Warnings | Duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| Golden 1 | 4 | `4 passed in 6.63s` | 0 | 0 | 0 | 0 | 6.63s |
| Golden 2 | 4 | `4 passed in 6.57s` | 0 | 0 | 0 | 0 | 6.57s |

## 13. Valid settlement outcome

Valid proof credits only the assigned GPU provider and supports withdrawal.

## 14. Invalid-proof refund outcome

Mutated stored output yields INVALID, credits only the AI user, and never the
provider.

## 15. Timeout-refund outcome

Refund reverts through the deadline and succeeds strictly afterward, including
while paused; withdrawal remains available.

## 16. Refund/settlement-race outcome

When the user refund wins, the pending verifier intent becomes obsolete and no
conflicting settlement broadcasts. Exactly one contract terminal state exists.

## 17. Full backend test counts

Collection reported exactly 334 tests.

| Suite | Collected | Passed | Failed | Errors | Skipped | Warnings | Duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| Default full | 334 | 334 | 0 | 0 | 0 | 0 | 54.15s |
| PostgreSQL | 64 | 64 | 0 | 0 | 0 | 0 | 34.75s |
| Anvil | 22 | 22 | 0 | 0 | 0 | 0 | 8.63s |
| ABI/artifact | 6 | 6 | 0 | 0 | 0 | 0 | 0.53s |
| Escrow receipt | 6 | 6 | 0 | 0 | 0 | 0 | 0.73s |
| Scheduler/dispatcher | 25 | 25 | 0 | 0 | 0 | 0 | 3.19s |
| Worker protocol | 10 | 10 | 0 | 0 | 0 | 0 | 1.21s |
| Proof verification | 28 | 28 | 0 | 0 | 0 | 0 | 2.85s |
| Settlement | 12 | 12 | 0 | 0 | 0 | 0 | 4.78s |
| Events/reconciliation | 38 | 38 | 0 | 0 | 0 | 0 | 5.07s |
| Concurrency/idempotency | 21 | 21 | 0 | 0 | 0 | 0 | 3.09s |
| E2E confirmation | 4 | 4 | 0 | 0 | 0 | 0 | 9.85s |
| Post-remediation E2E | 4 | 4 | 0 | 0 | 0 | 0 | 9.76s |
| Post-remediation full | 334 | 334 | 0 | 0 | 0 | 0 | 110.30s |

Focused groups overlap and are not summed into a synthetic total.

## 18. PostgreSQL and Anvil results

All 64 PostgreSQL and 22 dedicated Anvil tests passed with no skips. The four
E2E cases deploy additional fresh chains/contracts. Repeated runs prove retained
local audit rows do not contaminate later tests; evidence was not deleted to
manufacture cleanup.

## 19. Execution-order independence

The same deterministic list of 27 test modules ran in every full order.

| Order | Collected | Passed | Failed | Errors | Skipped | Warnings | Duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| Default | 334 | 334 | 0 | 0 | 0 | 0 | 54.15s |
| Reversed | 334 | 334 | 0 | 0 | 0 | 0 | 55.99s |
| Anvil first | 334 | 334 | 0 | 0 | 0 | 0 | 56.50s |
| PostgreSQL first | 334 | 334 | 0 | 0 | 0 | 0 | 57.40s |

## 20. Solidity, fuzz, invariant, gas and size

`forge fmt --check`, build, verbose tests, gas report and snapshot check passed.
`forge test`: **157 passed, 0 failed, 0 skipped in 4.17s**. Breakdown: 119
unit/fuzz, 18 config, 9 deployment, 5 smoke, 1 manual invariant-fuzz, and 5
stateful invariants. Fuzz runs=256; invariants=256 runs × 100 depth=25,600 calls
per invariant, `fail_on_revert=true`, zero handler reverts. CI uses 1,024 runs
and invariant depth 200. Snapshot success means no material gas baseline change.

Coverage (`--ir-minimum`, with Foundry's inaccurate-viaIR-mapping warning):
98.12% lines, 95.76% statements, 72.06% branches, 98.48% functions. Slither
is unavailable; no Slither pass is claimed.

## 21. Security verification

Executable coverage verifies canonical UUID/fingerprint/price, escrow/pending
accounting and solvency, SafeERC20 pull withdrawals, role/lease/deadline/state
binding, reassignment, replay rejection, EIP-712 domain and worker signer,
valid/invalid settlement, duplicate prevention, timeout/race mutual exclusion,
partial pause, reentrancy, adversarial tokens, events/errors, receipt authority,
durable outbox/nonces/retries, restart-safe events, and API/contract agreement.
PoAE remains trusted-backend tamper evidence, not proof against a malicious
worker.

## 22. Lint and formatting

`ruff check .` passed; `ruff format --check .` reported 78 files formatted.
`git diff --check`, artifact sync, and 15 deployment manifest/ignore tests pass.

## 23. Repository and secret hygiene

No real `.env`, PEM/key, venv, Foundry journal/cache, database, or Anvil state is
tracked/awaiting commit. Suppressed-value scanning found no seed phrase or
literal private-key assignment. Three credential-shaped URLs are documented
placeholders in examples/historical docs. Deterministic keys are test-only.

## 24. Pytest-asyncio warning disposition

The exact warning was:

> Overriding the "event_loop_policy" fixture is deprecated and will be removed
> in a future version of pytest-asyncio. Use the
> "pytest_asyncio_loop_factories" hook to customize event loop creation.

`conftest.py` now uses that supported hook with `uvloop.new_event_loop`,
preserving behavior without a warning filter. The declared development
dependency floor is `pytest-asyncio>=1.4.0`, the first project-supported version
for this hook. All final E2E/full/order/focused suites report zero warnings.

## 25. Remaining limitations

- Local PostgreSQL/Anvil only; no Arbitrum Sepolia evidence.
- Fixture executor, not real GPU inference; no live R2.
- No frontend/browser, Redis, IPFS, hosted, load, or beta claim.
- Slither unavailable; viaIR coverage warning retained.
- Development DB remains intentionally behind at `0003`; it was not modified.
- Existing strict-MyPy debt is out of this matrix; no MyPy-green claim.

## 26. Skill usage

All 14 repository-documented skills were discovered before this closure phase.

Applied:

1. `solidity-foundry-security`: threat, adversarial, invariant, coverage, gas,
   bytecode, ABI, and artifact verification.
2. `tdd`: reproduced the disconnected E2E behavior, repaired its stale client,
   and reran focused and full regression matrices.
3. `diagnosing-bugs`: isolated multipart-client and pytest-asyncio causes before
   making the smallest legitimate closure fixes.
4. `code-review`: independent Standards and Spec reviews of the final diff.

Not applied:

1. `domain-modeling`: `CONTEXT.md` vocabulary was consumed, but no domain term,
   model, or ADR changed.
2. `research`: canonical local source, artifacts, tests, and the supplied closure
   specification were sufficient; no external fact-finding was needed.
3. `codebase-design`: no new architectural interface or module seam was needed.
4. `grill-with-docs`: the closure specification was already explicit and no
   planning interrogation was required.
5. `improve-codebase-architecture`: no refactor was authorized or necessary.
6. `handoff`: no separate session-transition workflow was required; this report
   is the durable continuation record.
7. `ask-matt`: phase routing was already explicit in `AGENTS.md`.
8. `setup-matt-pocock-skills`: repository skills were already installed.
9. `teach`: this was verification and closure, not a teaching task.
10. `wizard`: no human-only provisioning, credentials, or deployment was in
    scope.

## 27. Final acceptance and verdict

All required local gates—two E2E runs, terminal outcomes, full/focused/order
suites, ABI/artifact, Foundry/fuzz/invariants/gas/snapshot, lint/format,
isolation/hygiene, and API/contract agreement—passed.

**Final verdict: PASS for the local Phase 3 Integration Closure.** This does not
authorize or claim Phase 4/5, testnet, GPU, browser, or production completion.

## 28. Files included in the closure commit

```text
backend/tests/conftest.py
backend/tests/test_integration_closure_e2e.py
backend/pyproject.toml
backend/uv.lock
docs/INTEGRATION_CLOSURE_REPORT.md
```

These are the only files authorized for the closure commit. No push occurred.

## 29. Recommended next ticket and report status

Resume from `docs/POST_PHASE3_SUB_TICKETS.md` and respect all owner/dependency
gates; this closure waives none. Any later code, migration, artifact, dependency,
or test change invalidates the affected evidence and requires rerunning it.
