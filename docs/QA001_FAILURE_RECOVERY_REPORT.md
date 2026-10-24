# QA-001 failure, concurrency, and recovery matrix

## Result

QA-001 is complete for the local disposable environment. The full backend
suite passed with PostgreSQL in Docker and disposable Anvil, and the complete
Foundry suite passed. The connected public Sepolia evidence remains documented
separately in the GCP-004/WRK-003 reports.

## Verification

- Backend: **416 passed** using
  `postgresql+asyncpg://...@127.0.0.1:55432/nebula_test`.
- Repeated integration closure: **4 passed + 4 passed**, covering valid and
  invalid proof, timeout/refund, settlement/refund race, event restart, and
  final API projection.
- Dedicated Anvil proof/settlement suite: **12 passed**.
- Foundry: **152 passed** (5 Smoke, 1 invariant, 9 deployment, 18 config,
  119 protocol/invariant tests).

The matrix covers worker failure and reassignment, stale leases, invalid proof,
refund and settlement races, pause behavior, duplicate requests/proofs/
settlements, dropped/reverted assignment handling, event backfill/restart,
database/chain reconciliation, concurrent scheduler/dispatcher behavior,
storage/input integrity, authentication and API authorization, signer separation,
and migration upgrades/downgrades.

The first full backend run exposed four stale test assertions (legacy readiness
JSON and migration head `0008` after the approved `0009` migration). Those tests
were updated to the current RFC problem response and migration head, then the
complete suite was rerun successfully.

## Scope boundary

This closes the local QA-001 matrix. QA-002 security closure and QA-003
long-duration reliability/performance/backup/soak evidence remain separate
tickets. Public beta acceptance is also not inferred from local tests.
