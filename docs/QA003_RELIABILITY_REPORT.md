# QA-003 reliability, performance, backup, and soak gate

## Current state

QA-003 is **PARTIAL**. All agent-runnable local reliability checks pass. The
remaining gates require an owner-approved staging window and must not be
simulated with local fixtures or the production Supabase database.

## Completed evidence

- PostgreSQL backup/restore rehearsal passed using Docker container
  `nebula-e2e-postgres`: `pg_dump -Fc nebula_test`, restore into the explicitly
  disposable `nebula_restore` database, and post-restore schema verification
  (`16` public tables).
- PostgreSQL concurrency, nonce coordination, and outbox recovery tests:
  **14 passed in 0.81s**.
- QA-001 full backend matrix: **416 passed**.
- Repeated PostgreSQL/Anvil integration closure: **4 + 4 passed**.
- Anvil protocol settlement suite: **12 passed**.
- Foundry contract suite: **152 passed**.
- Private storage integrity and event backfill/restart behavior are covered by
  the QA-001 and Phase 3 durability suites.
- Cloud Run bounded health sample against the current deployed origin: 20/20
  `/live` requests succeeded (p50 `230.6 ms`, p95 `22.0 s`, max `22.0 s`) and
  20/20 `/ready` requests succeeded (p50 `264.8 ms`, p95 `436.4 ms`). The
  `/live` tail reflects cold starts with the reviewed min-instances-zero
  configuration and is recorded as an operational observation, not hidden.
- The protected `CLOUD_RUN_ORIGIN` now matches the deployed service URL.
- Owner-created Supabase logical backup: custom archive with 673 TOC entries
  and 181 table/table-data entries; the archive is stored outside the repo and
  contains no repository secrets.

## Remaining owner-controlled gates

1. Run a 24-hour Worker soak with planned Worker/backend-runner restarts,
   recording job success/error rates and ensuring no silent GPU fallback.
2. Validate a staging-database backup and restore using the owner-approved
   Supabase procedure; do not run destructive restore commands against the live
   database without an explicit snapshot and rollback plan.
3. Run bounded RPC throttling/failure injection and confirm retry,
   reconciliation, and nonce behavior under the staging RPC provider.
4. Execute a five-or-more-job staging load sample and publish p50/p95/p99
   latency, throughput, error rate, storage bytes, and runner capacity.
5. Review Cloud Run/Vercel/Supabase/R2 monitoring, budgets, retention, and
   rollback evidence during the same owner-approved window.

These gates depend on real staging capacity, credentials, billing/monitoring
approval, and a time window longer than a normal test run. QA-003 therefore
remains partial; OPS-001 can prepare the reviewed staging/monitoring wizard,
but OPS-002/OPS-003 and REL-001 must wait for these measurements.
