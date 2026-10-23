# BE-003 Completion Report

## Outcome

BE-003 is complete. Provider node and earnings interfaces are authenticated
and owner-scoped, credential and worker-signer rotation are enforced, finalized
withdrawals reconcile into durable history, browser-facing problems are
normalized, and checked OpenAPI types cannot silently drift during backend
tests or frontend builds.

## Delivered

- Provider-only node registration, listing, detail, API-key rotation/revocation,
  and worker-signer rotation.
- Display-once plaintext API credentials; only hashes are persisted.
- Provider-scoped credit history, credited/withdrawn totals, and safe read-only
  pending-withdrawal reporting.
- Finality-gated, overlap-idempotent `WithdrawalCompleted` projection and the
  `0009_payment_withdrawal_history` migration.
- RFC 7807-shaped `application/problem+json` responses without traces or
  infrastructure secrets.
- Checked `backend/openapi.json` and generated
  `frontend/src/api/schema.d.ts`, with backend and frontend drift gates.
- Behavioral coverage for ownership, redaction, rotation, revocation,
  withdrawal projection, and stale worker-signer rejection.

## Verification

- Backend focused/integration set: 72 passed, 41 PostgreSQL-only tests skipped
  when no test PostgreSQL URL was supplied.
- Final BE-003 focused set: 18 passed.
- Ruff and `git diff --check`: passed.
- Frontend lint: passed.
- Frontend Vitest: 3 passed.
- Frontend production build, including Node-only OpenAPI drift check: passed.
- Alembic lineage: `0009_payment_withdrawal_history` is the single head.
- Independent standards/spec reviews: no remaining medium/high findings.

The live Supabase database was not mutated during local verification. Apply
Alembic revision `0009_payment_withdrawal_history` as part of the next reviewed
backend deployment.

## Phase 2 Skill Usage

### Discovered Skills

- solidity-foundry-security, tdd, domain-modeling, code-review,
  diagnosing-bugs, research, codebase-design, grill-with-docs,
  improve-codebase-architecture, handoff, ask-matt,
  setup-matt-pocock-skills, teach, wizard.

### Applied Skills

1. **tdd**: Added failing provider earnings/node/withdrawal and stale-signer
   tests before implementing each interface.
2. **domain-modeling**: Kept provider credits, pull-payment withdrawals, nodes,
   credentials, and worker signers aligned with `CONTEXT.md` and PRD v3.1.
3. **diagnosing-bugs**: Diagnosed E2E Docker stopped-container and refresh-cookie
   path failures before BE-003 work.
4. **code-review**: Ran independent standards and specification reviews, then
   resolved every medium/high finding and repeated review.

### Not Applied

- **solidity-foundry-security**: No smart-contract source was changed.
- **research**: No external API uncertainty required a research artifact.
- **codebase-design**: Existing backend service/router seams were sufficient.
- **wizard**: BE-003 required no human-only setup step.
- **grill-with-docs**, **improve-codebase-architecture**, **handoff**,
  **ask-matt**, **setup-matt-pocock-skills**, **teach**: not needed for this
  implementation phase.
