# Nebula AI Cloud Post-Phase-3 Sub-Tickets

Status: planning backlog; no ticket in this file is evidence of implementation
Prepared: 2026-09-09
Parent plan: `docs/POST_PHASE3_EXECUTION_ROADMAP.md`
Verified implementation baseline: `7fc457f`

This backlog divides the post-Phase-3 roadmap into independently reviewable
tickets. The parent roadmap remains authoritative for architecture, security
invariants, commands, human procedures, and stop conditions. A future agent
must read both documents completely before starting work.

## Bounded execution-order override — 2026-09-10

The owner explicitly requested the next three owner-independent tickets while
unavailable. BE-001, WRK-001, and WRK-002 agent-local work therefore proceeded
out of rollout order. This does not waive dependencies or acceptance gates:
public artifact coordinates, topology approval, testnet deployment, target-GPU
validation, and real-system settlement remain blocked; worker tickets remain
`PARTIAL`. No frontend implementation was started.

## Ticket rules

- Ticket states are `BLOCKED`, `READY`, `IN PROGRESS`, `VERIFY`, or `DONE`.
- `DONE` requires acceptance evidence; a code diff alone is not completion.
- Dependencies are hard gates. Do not start a dependent ticket early merely to
  save time.
- `AGENT` tickets may be completed locally without owner secrets or external
  side effects. `OWNER` tickets require the owner. `JOINT` tickets require an
  agent to prepare and validate the operation and the owner to authorize the
  exact external action.
- Testnet broadcast, explorer publication, faucet use, hosted-resource changes,
  secrets, expenses, DNS, deployment, push, merge, tag, and release always need
  explicit owner authorization even if a ticket is otherwise ready.
- Contract behavior and interface changes are outside this backlog unless a
  blocking defect is documented and the owner separately approves a new
  threat-modeled Solidity slice.
- Every implementation ticket follows test-first development where practical,
  focused verification, affected Phase 1-3 regressions, artifact/secret checks,
  and a fixed-base standards/spec review.
- Never mark a hardware-, browser-, owner-, or public-network-dependent gate as
  passed using a fake, skipped test, direct database mutation, or privileged
  contract shortcut.

## Dependency graph

```text
DPL-001 -> DPL-002 -> DPL-003 -> DPL-004 -> DPL-005
                                      |
                                      v
HUM-001 -> HUM-002 -> HUM-003 -> NET-001 -> NET-002 -> NET-003
                                               |
                                               v
BE-001 -> BE-002 -> BE-003 -> FE-001 -> FE-002 -> FE-003 -> FE-004
                         \                         /
                          +------> WRK-001 -> WRK-002 -> WRK-003
                                                   |
                                                   v
QA-001 -> QA-002 -> QA-003 -> OPS-001 -> OPS-002 -> OPS-003 -> REL-001
```

The diagram shows the primary critical path. Each ticket's `Depends on` field
is definitive where the diagram is intentionally simplified.

## Milestone A — Local deployment readiness (owner absent)

### DPL-001 — Deployment configuration contract and threat model

- State: `DONE`
- Actor: `AGENT`
- Depends on: none
- Outcome: define one validated deployment configuration interface for local
  Anvil and Arbitrum Sepolia without accepting worker/provider identities as
  verifier inputs.
- Deliverables: threat model; configuration fields and validation errors;
  tests that initially fail for zero addresses, wrong chain, missing USDC code,
  non-6-decimal token, zero price, and price above maximum.
- Acceptance: the validator has no broadcast capability; no key is logged or
  serialized; Sepolia requires chain ID `421614`; contract domain terminology
  matches `CONTEXT.md`. DPL-002 must prove its deployment entry point invokes
  this validator before starting broadcast.
- Verify: focused Foundry tests, `forge fmt --check`, `forge build`.

### DPL-002 — Foundry deployment script

- State: `DONE`
- Actor: `AGENT`
- Depends on: DPL-001
- Outcome: add `contracts/script/Deploy.s.sol` using the validated interface.
- Deliverables: deploy with configured USDC; set backend verifier; optionally
  set price/cap; transfer ownership last; assert token, verifier, owner, price,
  cap, pause state, zero accounting, and solvency from getters.
- Acceptance: tests prove privileged calls occur before ownership transfer and
  reject invalid configurations; no contract behavior/interface change; no
  real broadcast.
- Verify: `forge test --match-path test/Deploy.t.sol`, then full Foundry suite.

### DPL-003 — Bounded local lifecycle smoke script

- State: `DONE`
- Actor: `AGENT`
- Depends on: DPL-002
- Outcome: add `contracts/script/Smoke.s.sol` for a complete Anvil lifecycle.
- Deliverables: distinct deployer/owner, verifier, AI user, GPU provider, and
  worker signer identities; MockUSDC funding; approve, create, assign, submit,
  valid settle, pending withdrawal, and withdrawal.
- Acceptance: asserts unauthorized assignment/settlement failure, invalid
  verdict refund, duplicate settlement rejection, pause behavior, and solvency;
  reuses canonical ABI/UUID/proof helpers.
- Verify: script succeeds twice against two fresh Anvil processes.

### DPL-004 — Sanitized deployment manifest and validator

- State: `DONE`
- Actor: `AGENT`
- Depends on: DPL-002
- Outcome: introduce a public-only deployment manifest schema and deterministic
  validation command.
- Deliverables: placeholder/schema fixture under `contracts/deployments/` and
  validator under `scripts/`; fields listed in parent roadmap section 5.3;
  `.gitignore` coverage for Foundry broadcast journals and secret env files.
- Acceptance: rejects placeholder-as-deployed claims, wrong chain/address/hash,
  missing receipt/block/compiler settings, and secret-like fields; understands
  that immutable USDC makes raw runtime/template hashes differ.
- Verify: validator positive/negative tests and
  `python scripts/sync_contract_artifacts.py --check`.

### DPL-005 — Deployment runbook and local readiness report

- State: `DONE`
- Actor: `AGENT`
- Depends on: DPL-003, DPL-004
- Outcome: make deployment reproducible by a new operator without granting
  implicit permission to broadcast.
- Deliverables: `docs/runbooks/ARBITRUM_SEPOLIA_DEPLOYMENT.md`; exact preflight,
  rehearsal, broadcast-preview, verification, recovery, manifest, and rollback
  procedures; slice completion report using roadmap section 17.
- Acceptance: all Stage 1 commands pass, both fresh-Anvil rehearsals pass, full
  backend regression is green with zero required skips against `nebula_test`,
  artifact sync is clean, and report explicitly states no external transaction
  was broadcast.
- Verify: parent roadmap section 5.5 plus secret scan and `git diff --check`.

## Milestone B — Owner-controlled testnet prerequisites

### HUM-001 — Approve identity map and custody model

- State: `DONE`
- Actor: `OWNER`
- Depends on: DPL-005
- Outcome: approve public addresses for deployer, owner, backend verifier, AI
  user, provider payout, and worker signer with the separations in section 6.1.
- Owner steps: create/select wallets; keep seed phrases/private keys outside
  chat and Git; use an encrypted keystore or ignored `chmod 600` env; supply
  only public addresses to the agent.
- Acceptance: verifier is distinct from user/provider/worker; secret files pass
  `git check-ignore -v`; ownership-transfer intent is explicitly recorded.

### HUM-002 — Provision testnet assets

- State: `DONE`
- Actor: `OWNER`
- Depends on: HUM-001
- Outcome: provision only testnet gas and Circle testnet USDC.
- Owner steps: verify Arbitrum Sepolia chain ID `421614`; obtain ETH for every
  gas-paying role; obtain ARB USDC for the AI user from Circle; verify balances
  and token address on the explorer.
- Acceptance: official current USDC address is rechecked; agent receives public
  balances/addresses only; no mainnet asset is involved.

### HUM-003 — Provision RPC and explorer credentials

- State: `DONE`
- Actor: `OWNER`
- Depends on: HUM-001
- Outcome: provide a reliable HTTPS Arbitrum Sepolia RPC and optional explorer
  verification key through ignored local/hosted secrets.
- Owner steps: restrict provider project to testnet where possible; set quotas
  and spend limits; do not assume the example WebSocket endpoint works; never
  paste credential-bearing URLs or keys into chat.
- Acceptance: RPC returns `421614`; secret placement is validated without
  printing values; HTTP log polling remains the supported baseline.

## Milestone C — Public contract and connected-runtime smoke

### NET-001 — Testnet deployment preflight and owner authorization

- State: `DONE WITH PROCESS EXCEPTIONS` (the deployed result matches the
  preview, but retrospective review found clean-tree and authorization-record
  deviations documented in the NET-002 report)
- Actor: `JOINT`
- Depends on: HUM-002, HUM-003
- Outcome: produce the exact no-broadcast deployment preview for owner review.
- Deliverables: source commit/tree state, chain ID, public role addresses, USDC,
  public balances, transaction sequence, gas estimate, artifact hashes,
  rehearsal evidence, and ownership-transfer statement.
- Acceptance: owner explicitly authorizes this exact deployment; any mismatch
  stops the ticket. Authorization to inspect is not authorization to broadcast.

### NET-002 — Deploy, verify, and publish sanitized manifest

- State: `DONE`
- Actor: `JOINT`
- Depends on: NET-001
- Outcome: execute the reviewed Foundry script once on Arbitrum Sepolia and
  verify the deployed source.
- Deliverables: receipt, contract address/block, getter readbacks, code hash,
  explorer verification, finalized sanitized manifest, and deployment report.
- Acceptance: token/owner/verifier/price/cap/pause/accounting/solvency match;
  failed source verification is repaired on the existing deployment rather
  than redeploying; deployment block is exact, not zero.

### NET-003 — Connected Sepolia runtime smoke

- State: `DONE`
- Actor: `JOINT`
- Depends on: NET-002
- Outcome: prove the real backend runners and deterministic fixture worker use
  the deployed contract correctly.
- Deliverables: isolated `nebula_sepolia` database/storage; API plus independent
  receipt, assignment, settlement, event, and reconciliation runners; two full
  public-interface journeys with distinct UUIDs; provider withdrawal.
- Acceptance: no fabricated receipts/logs, fake blockchain adapter, direct DB
  lifecycle shortcut, or privileged test call; final API, PostgreSQL projection,
  contract state, receipts, and logs agree; nonce/cursor/idempotency survive the
  second run.

## Milestone D — Browser/backend prerequisite interfaces

### BE-001 — Authoritative bounded input upload

- State: `DONE` (local implementation and validation; public validation remains gated by NET-003)
- Actor: `AGENT`
- Depends on: none for local implementation; NET-003 before public validation
- Outcome: backend—not browser—derives the job fingerprint from exact accepted
  input bytes and approved model/protocol metadata.
- Deliverables: authenticated streamed upload/interface; server job UUID and
  private storage key; size/MIME/extension/magic/dimension checks; SHA-256;
  atomic cleanup and idempotency; migrations only if unavoidable.
- Acceptance: `POST /v1/jobs` no longer trusts arbitrary client storage keys or
  hashes in the live browser path; row locks are not held during storage I/O;
  tests cover truncation, over-limit, mismatch, traversal, duplicate, and
  cleanup behavior.

### BE-002 — Browser auth topology ADR and implementation

- State: `DONE` (GCP-005 production rewrite and genuine browser acceptance passed 2026-10-23)
- Actor: `AGENT` for local work; `OWNER` approves topology
- Depends on: BE-001
- Outcome: resolve the refresh cookie path/topology and enforce a coherent
  wallet-auth browser security model.
- Deliverables: ADR; HttpOnly/Secure refresh cookie, in-memory access token,
  aligned route/proxy/path, CORS, Origin/CSRF checks, rotation/reuse revocation,
  and logout behavior.
- Acceptance: tests cover challenge reuse/expiry, wallet mismatch, token expiry,
  rotation, reuse, logout, cookie flags/path, and allowed/disallowed origins.

### BE-003 — Provider interfaces and stable browser contract

- State: `DONE`
- Actor: `AGENT`
- Depends on: BE-002, NET-003
- Outcome: replace provider placeholders and provide generated, stable browser
  request/response/error types.
- Deliverables: provider-scoped nodes; earnings/credit history; safe on-chain
  pending withdrawal; API-key display-once/rotation/revocation; worker-signer
  rotation/stale rejection; normalized problem responses; OpenAPI generation or
  validation.
- Acceptance: `/v1/earnings` is no longer a placeholder; authorization and
  redaction tests pass; browser types cannot silently diverge from FastAPI.

## Milestone E — Thin frontend vertical slice

### FE-001 — Frontend test harness and generated contract/OpenAPI artifacts

- State: `DONE`
- Actor: `AGENT`
- Depends on: BE-003, NET-002
- Outcome: create reliable frontend verification and eliminate handwritten ABI
  or request/response drift.
- Deliverables: Vitest/React Testing Library and browser harness; `npm test`;
  canonical generated contract artifact and OpenAPI types; staleness checks.
- Acceptance: no private values enter `VITE_*`; lockfile is pinned; lint, tests,
  and build pass without a broad framework upgrade.

### FE-002 — Wallet authentication and typed HTTP module

- State: `DONE`
- Actor: `AGENT`
- Depends on: FE-001
- Outcome: connect an Arbitrum Sepolia wallet, authenticate, and call backend
  interfaces safely.
- Deliverables: wrong-network handling; account/chain invalidation; challenge
  signing; in-memory access token; one refresh/retry path; cancellation; safe
  errors and zero token logging.
- Acceptance: deterministic adapter tests cover rejection, expiry, refresh,
  account change, chain change, backend outage, and unmount cancellation.

### FE-003 — AI-user upload and escrow journey

- State: `READY`
- Actor: `AGENT`
- Depends on: FE-002, BE-001
- Outcome: implement the browser path through upload, allowance, approval,
  `createJob`, receipt, and escrow confirmation.
- Deliverables: backend model selection; bounded ResNet input upload; on-chain
  `jobPrice`/allowance read; exact approval; clear signing summary; receipt
  handling; confirm endpoint receives only transaction hash.
- Acceptance: rejection, insufficient ETH/USDC, wrong chain, approval failure,
  replaced/dropped/reverted receipt, retry, and duplicate prevention tests pass.

### FE-004 — Job lifecycle, reconciliation, and result UX

- State: `BLOCKED`
- Actor: `AGENT` locally; `JOINT` for Sepolia browser run
- Depends on: FE-003, NET-003
- Outcome: show the authoritative job lifecycle and return an authorized result.
- Deliverables: visibility-aware polling/backoff/cancellation; DB/on-chain/proof/
  lease/attempt/payment/refund/reconciliation states; explorer links; authorized
  result download without exposing storage keys.
- Acceptance: real browser+Anvil journey passes; then owner-authorized Sepolia
  browser journey passes without DB manipulation or privileged calls.

## Milestone F — Real ResNet50 worker

### WRK-001 — Safe model registry, loader, and cache

- State: `PARTIAL` (agent-local implementation complete; immutable production artifact URL/hash remain owner/infrastructure-gated)
- Actor: `AGENT`
- Depends on: BE-001 for final model metadata contract
- Outcome: load one approved ResNet50 artifact safely behind the existing
  executor seam.
- Deliverables: code-defined pinned architecture; `safetensors` state dict;
  streamed bounded download; pre-parse SHA-256; temp file plus atomic rename;
  hash-keyed locked cache; 24-hour freshness; corrupt/partial cleanup.
- Acceptance: arbitrary pickle/remote code rejected; `merkletools` removed;
  concurrent, timeout, hash mismatch, partial download, and in-use cache tests.

### WRK-002 — Deterministic ResNet50 execution and fixed checkpoints

- State: `PARTIAL` (agent-local CPU implementation complete; target-GPU and live-system gates remain owner/hardware-gated)
- Actor: `AGENT`
- Depends on: WRK-001
- Outcome: add `ResNet50Executor` while retaining
  `DeterministicFixtureExecutor` for protocol tests.
- Deliverables: pinned preprocessing; inference mode; determinism settings;
  canonical top-k JSON; exact ordered `preprocess`, `forward`, `softmax`, `topk`
  checkpoint bytes/hashes; no dynamic `model.children()` tracer.
- Acceptance: at least ten CPU golden vectors, restart repeatability, bounded
  image/decompression/GPU-memory failure handling, and backend/worker fingerprint,
  Merkle, and EIP-712 convergence.

### WRK-003 — Worker signer migration and real-model system gates

- State: `BLOCKED`
- Actor: `AGENT` locally; `OWNER` for GPU/testnet access
- Depends on: WRK-002, NET-003
- Outcome: productionize configuration and prove the adapter through settlement.
- Deliverables: deliberate `PRIVATE_KEY` to `WORKER_SIGNING_PRIVATE_KEY`
  compatibility/deprecation path; stale signer/lease tests; crash/retry tests;
  local Anvil real-model settlement; target-NVIDIA repeat run.
- Acceptance: worker signer has no funds and is not provider/verifier; GPU gate
  is reported blocked—not skipped—until hardware exists; owner-authorized
  Sepolia real-model settlement passes before completion.

## Milestone G — Integration, security, and reliability closure

### QA-001 — Failure, concurrency, and recovery E2E matrix

- State: `BLOCKED`
- Actor: `AGENT` locally; `JOINT` for public staging cases
- Depends on: FE-004, WRK-003
- Outcome: automate all system journeys in roadmap section 12.1.
- Deliverables: valid/invalid proof, worker death/reassignment, stale worker,
  backend/RPC failure windows, event restart/backfill, chain-success/DB-failure,
  2+ workers, 5+ jobs, duplicate requests, verifier/refund race, pause, and
  reconciliation cases.
- Acceptance: authentic receipts/logs and public interfaces; existing 321
  backend and 125 Foundry tests remain green; no required skip.

### QA-002 — Application and protocol security closure

- State: `BLOCKED`
- Actor: `AGENT`
- Depends on: QA-001
- Outcome: execute and document roadmap section 12.2 threat tests and reviews.
- Deliverables: OWASP browser/API model; injection/XSS/upload/auth/CORS/CSRF/key
  lifecycle/role separation/RPC/storage/dependency/container/secret tests;
  Solidity standards/spec review and invariant evidence.
- Acceptance: no open critical/high finding; PoAE is described as authenticated
  commitment/protocol verification under a trusted backend verifier, never as
  trustless or zero knowledge.

### QA-003 — Reliability, performance, backup, and soak gate

- State: `BLOCKED`
- Actor: `JOINT`
- Depends on: QA-002
- Outcome: establish measured operational limits and recovery evidence.
- Deliverables: 24-hour worker soak with restarts; backend runner restarts;
  database backup/restore; RPC throttling; event backfill; storage integrity;
  5+ job p50/p95/p99/error rate; nonce contention and capacity checks.
- Acceptance: published test environment and measurements; no silent GPU skip;
  no open critical/high defect.

## Milestone H — Hosted staging and release readiness

### OPS-001 — Local deployment configuration and human provisioning wizard

- State: `BLOCKED`
- Actor: `AGENT` prepares; `OWNER` reviews and runs
- Depends on: QA-003
- Outcome: prepare reviewed hosting definitions and an interactive wizard for
  steps only the owner can perform.
- Deliverables: Docker/process/workflow/infrastructure configuration as needed;
  wizard for Supabase, private R2, OCI Always Free, Vercel Hobby, RPC,
  monitoring, free DNS, CI
  environments, secrets, budgets, and confirmations.
- Acceptance: wizard never echoes secrets or performs irreversible actions
  without immediate confirmation; agent does not provision accounts/resources.

### OPS-002 — Owner provisions hosted staging

- State: `BLOCKED`
- Actor: `OWNER`
- Depends on: OPS-001
- Outcome: create and approve external staging resources, budgets, connections,
  and protected secrets.
- Acceptance: least privilege; separate staging database/bucket; no secrets in
  repository/frontend; DNS and account changes are explicitly authorized.

### OPS-003 — Deploy and validate hosted staging

- State: `BLOCKED`
- Actor: `JOINT`
- Depends on: OPS-002
- Outcome: deploy API, every independent runner, frontend, storage, database,
  and monitoring with consistent chain/artifact configuration.
- Acceptance: roadmap section 13.3 passes, including empty/current Alembic
  upgrades, readiness failures, private objects, auth topology, cross-runtime
  contract/domain agreement, monitoring, restore/rollback, and ten consecutive
  reconciled public staging jobs.

### REL-001 — Beta evidence and launch-readiness decision

- State: `BLOCKED`
- Actor: `JOINT`
- Depends on: OPS-003
- Outcome: finish documentation/browser coverage and run a small testnet beta.
- Deliverables: README, architecture/security/PoAE limits, worker and operations
  guides; Chrome/Firefox/Safari/mobile evidence; at least five AI users and one
  external GPU provider; payout, tamper/refund, reassignment, reconciliation
  demonstrations; severity triage.
- Acceptance: no critical/high defects and an explicit owner go/no-go decision;
  this ticket does not authorize mainnet or real-value assets.

## Recommended execution batches

Do not merge tickets into one broad change. The recommended sequence is:

1. Owner absent: DPL-001 through DPL-005 only.
2. Owner returns: HUM-001 through NET-003.
3. Local product work: BE-001 through BE-003, then FE-001 through FE-004.
4. Real inference: WRK-001 through WRK-003.
5. Release gates: QA-001 through QA-003.
6. Hosted staging and beta: OPS-001 through REL-001.

BE-001 may be prepared locally while waiting for owner-controlled testnet work,
but it must remain a separate branch/diff and cannot be declared publicly
validated until NET-003. Do not begin broad frontend or worker implementation
while Stage 1 is unfinished.

## Per-ticket handoff template

```text
Ticket:
State:
Starting commit and pre-existing dirty files:
Skills discovered/applied/not applied:
Acceptance criteria addressed:
Files changed:
Tests written first and observed red result:
Implementation summary:
Commands and machine-derived results:
Phase 1-3 regression result:
Artifact and secret checks:
External actions and owner authorization:
Known limitations/blockers:
Uncommitted files:
Next unblocked ticket:
```

## Planning skill record

### Discovered repository inventory

`solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`,
`diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`,
`improve-codebase-architecture`, `handoff`, `ask-matt`,
`setup-matt-pocock-skills`, `teach`, and `wizard`.

The active skill catalog does not currently expose every skill named by
`AGENTS.md`; future agents must rediscover availability at ticket start.

### Applied

1. `codebase-design`: tickets follow existing interfaces and separate contract
   deployment, backend storage/auth, browser, worker execution, and operations
   at their real seams.
2. `domain-modeling`: ticket language preserves AI user, GPU provider, GPU node,
   worker signer, backend verifier, lease, proof, verdict, and settlement as
   distinct domain concepts. No glossary decision changed, so `CONTEXT.md` did
   not require an edit.

### Not applied

- `solidity-foundry-security`: no Solidity or Foundry behavior was implemented;
  it is mandatory beginning with DPL-001.
- `tdd`: this change creates planning tickets only; implementation tickets
  explicitly require red-green verification.
- `code-review`: no implementation slice was reviewed; each completed ticket
  requires a fixed-base standards/spec review.
- `diagnosing-bugs`: no failing behavior was diagnosed.
- `research`: no new external facts were required; the parent roadmap already
  records primary-source network facts and requires revalidation at execution.
- `wizard`: human-only stages were ticketed, but no executable wizard was
  created; it is required for OPS-001 and may be prepared after Stage 1 review.
- Remaining routing, refactoring, teaching, setup, and handoff skills were not
  needed to divide the approved roadmap.
