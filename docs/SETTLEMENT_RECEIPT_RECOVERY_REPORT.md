# Settlement receipt recovery

## Verified cause

Live job `6738dd18-7786-5b4a-ad49-98550fc2925c` remained `settling` with an active lease even though transaction `0x9fdf0b44dcff3d2386ca9eed2c6d56bdcdaf20dbe2b6f5b5aee29b2c9f043871` succeeded at Arbitrum Sepolia block **323154202**. The live historical cursor was **322854656** and the database contained no events from that settlement receipt.

The coordinator confirmed its transaction outbox record without recording or projecting the receipt events. The dashboard requires both `status=completed` and canonical `on_chain_state=Settled`; provider withdrawal is independent. Relinking unassociated events cannot recover events that have never been ingested.

## Changes

- The settlement runner records canonical receipt events through the same projector used by historical ingestion, without moving the historical cursor.
- Recovery includes already-confirmed settlements and stale finalized settlements. Confirmed proof receipts continue toward settlement, while finalized proof receipts cannot monopolize the recovery batch.
- Receipt validation binds the contract emitter, chain instance, exact job ID, transaction hash, canonical block hash, and confirmation/finality depths.
- Canonical settlement completes the job, lease, and attempt, and recomputes the GPU node's active lease count. Repeated processing preserves a single payment credit.
- Historical scans and receipt recovery serialize job projection. First-cursor creation is atomic and reorg handling cannot jump over unscanned history.
- Reconciliation only rebuilds terminal outcomes. Old assignment evidence cannot regress running/verifying jobs or revive failed leases. Older pending events cannot suppress a confirmed terminal outcome.
- Unassociated-event relinking is scoped to the job's escrow chain, genesis, and contract.

The smart contract, refund eligibility, pricing, model execution, and wallet custody rules are unchanged.

## Verification

The new regression suite initially failed on the live symptom and on three regressions from replaying older assignment events. Its 25 cases now cover receipt recovery, replay, finality, chain isolation, expired leases, backlog, batch starvation, and late proof confirmation.

Completed checks:

- Backend and script suites: **485 passed, 71 skipped** (PostgreSQL coverage run separately).
- PostgreSQL/Anvil integration suites: **70 passed**.
- Worker suite: **52 passed, 2 skipped**.
- Frontend unit tests: **80 passed**; lint, TypeScript, artifact checks, and production build passed.
- Deployed production browser authentication smoke: **1 passed**.
- Ruff on changed Python files: passed.
- Mypy was executed. Baseline comparison at `fbf6133` found **108 existing errors** in the three affected production files, predominantly legacy SQLAlchemy model typing. This check is not clean; this release does not migrate the ORM typing system.

Live canonical receipt recovery sent no blockchain transactions. The deployed same-origin job API subsequently returned:

```json
{
  "status": "completed",
  "on_chain_state": "Settled",
  "current_lease_status": "completed",
  "provider_payment_credit_status": "credited",
  "reconciliation_health": "match"
}
```

The associated node's active lease count was verified as **0**.

## Runtime requirement

Cloud Run hosts the API only. The owner settlement runner must load the updated code to recover future receipts immediately. Updating the Cloud Run image alone cannot replace an already-running laptop Python process. The provider Worker can continue using its existing node identity and credentials.

## Skill usage

Discovered repository inventory: solidity-foundry-security, tdd, domain-modeling, code-review, diagnosing-bugs, research, codebase-design, grill-with-docs, improve-codebase-architecture, handoff, ask-matt, setup-matt-pocock-skills, teach, wizard. Additional installed presentation/design skills were inspected by inventory and are outside this backend change.

Applied: diagnosing-bugs for the live receipt/database feedback loop; tdd for failing runner/API regressions before the fix; codebase-design for sharing the durable receipt/scanner projection; code-review for separate standards and behavior reviews. CONTEXT.md supplied existing domain vocabulary; no domain model changed.

Not applied: contract security (no contract changes), research (no external API research needed), planning/refactoring/teaching/routing/setup/handoff skills (not the requested work), wizard (deployment and runner restart use existing protected configuration and need no new human-only setup). Frontend code is unchanged; its existing checks were run.
