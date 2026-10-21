# Phase 3 Integration Closure — Project Snapshot

Snapshot date: 2026-09-08
Base commit: `9dfdd87f562e48b122962676d769188157b7475c`
Status: **implemented and verified locally; not deployed**

The authoritative implementation report is
`docs/INTEGRATION_CLOSURE_REPORT.md`. This snapshot is the compact continuation
point for another agent; it supersedes the earlier pause-point checklist.

The approved continuation sequence is recorded in
`docs/POST_PHASE3_EXECUTION_ROADMAP.md`. A new agent must start there and begin
with its local-only Stage 1 deployment-readiness slice.

## Established runtime path

```text
HTTP API -> PostgreSQL -> scheduler -> assignment dispatcher
-> real Anvil NebulaVerifiableAI -> protocol worker -> real ProofVerifier
-> submitProof -> verifyJob -> eth_getLogs event poller
-> PostgreSQL projection/reconciliation -> GET /v1/jobs/{id}
```

The four authoritative journeys cover valid settlement/provider withdrawal,
invalid output/refund, paused timeout recovery, and the settlement/refund race.
They use ASGI HTTP, migrated `nebula_test`, fresh Anvil deployments, canonical
Foundry artifacts, real runners, the real 12-check verifier, and exact stored
bytes. No `FakeBlockchainBackend` is used in these journeys.

## Key implementation locations

- Canonical artifacts: `scripts/sync_contract_artifacts.py`,
  `backend/app/nebula_abi.json`, `backend/app/nebula_artifact.json`
- Schema: `backend/alembic/versions/0004_*` through `0008_*`
- Runtime: `backend/app/runners.py`, `runtime.py`, and services
  `chain_outbox.py`, `escrow_confirmation.py`, `assignment_dispatcher.py`,
  `settlement_coordinator.py`, `blockchain_events.py`, `retry_policy.py`
- Public seams: `backend/app/routers/jobs.py` and `worker.py`
- Minimal worker: `worker/worker.py`, `core/fixture_executor.py`, and
  `proof/envelope.py`
- Authoritative E2E: `backend/tests/test_integration_closure_e2e.py`
- Final details and limitations: `docs/INTEGRATION_CLOSURE_REPORT.md`

## Final verification identity

```text
ABI SHA-256:              57a205796f5ea3e9189e281af31dcdc337386075f1ae8060a0d34fe3c5aaf0e9
Runtime bytecode SHA-256: 54b4029baa8f1487adda2c3f7a676b54524ec8a591b61f843e63d349aa58faef
Compiler:                 0.8.20+commit.a1b79de6
Alembic head:             0008_proof_verification_claims
Backend tests:            321 passed, 0 skipped (all four required orders)
E2E repeat:               4 passed, then 4 passed
Foundry:                  125 passed, 0 failed, 0 skipped
```

Ruff, formatting, artifact staleness, Foundry formatting/build/gas/snapshot,
PostgreSQL migration, Anvil, restart, race, and concurrency gates pass. Strict
`mypy app` remains a disclosed pre-existing repository limitation (324 errors)
and must not be represented as green.

## Scope boundary and next action

No Arbitrum Sepolia deployment, frontend, Redis, live R2/IPFS, or real GPU
adapter was started. Before later work, read the original closure specification,
`AGENTS.md`, `CONTEXT.md`, and the final report. Do not redo or bypass this flow;
build the next phase on its public interfaces and preserve the canonical ABI,
EIP-712 domain, lease/deadline checks, durable outbox, and event projections.
