# WRK-003 real-model runtime repair and live evidence

Date: 2026-10-24 (UTC)  
Ticket state: **DONE** — target-GPU, owner-authorized integrated Sepolia, database
recovery, and disposable Anvil protocol gates passed.

## Outcome

Two distinct jobs executed the approved ResNet50 safetensors artifact on the
NVIDIA GeForce RTX 3050 Laptop GPU, completed proof verification and settlement
on Arbitrum Sepolia, reconciled through the event runner, and returned authorized
private-storage results matching the offline GPU preflight. The first job was
resumed using its existing escrow; it was not funded a second time.

The successful run used the existing Cloud Run API, private R2, hosted PostgreSQL,
and temporary laptop Worker/backend runners. No contract was changed or deployed.
The Cloud Run image was **not** redeployed with these local runner repairs.
All temporary probe/recovery Python processes were stopped afterward.

## Causes and repairs

1. **Corrupt smoke PNG:** the fixture executor never decoded its input, masking
   an invalid PNG. Real Pillow decoding failed. The probe now supplies a valid
   RGB PNG; malformed-image `SyntaxError` is also a bounded model-execution error.
2. **Premature retry:** closing a failed local attempt did not end its confirmed
   on-chain lease. The scheduler now waits through strict lease expiry before
   reassignment and continues selecting other eligible jobs. Reverted assignments
   close their pending attempts, without overwriting terminal/proof-processing
   job state during late recovery.
3. **Stale hosted schema:** the database was at migration `0008`, while current
   payment-history code required `0009_payment_withdrawal_history`. The existing
   additive migration was reviewed and applied. A read-only schema preflight now
   refuses mismatched revisions before model provisioning or live transactions;
   it never automatically migrates a database.
4. **Historical withdrawal projection:** older runners had persisted finalized
   withdrawals without projecting their payments. Replaying a later withdrawal
   incorrectly included those earlier credits and future credits. Projection now
   replays canonical finalized withdrawals in order and selects credits strictly
   before each withdrawal's chain/log position, preserving exact amount checks,
   chain/contract scope, and idempotence. Recovery used the normal event runner,
   not manual ledger/job-status updates.
5. **Large artifact delivery and preflight:** the model exceeded the hosted API's
   response-size limit. An owner-supplied private artifact URL can deliver it
   directly without forwarding the backend API key. The existing bounded loader
   still verifies the lease-bound SHA-256 before parsing safetensors. Streams
   close immediately on failure/byte-limit abort. Before live writes, preflight
   verifies actual artifact delivery and repeats genuine inference within and
   across fresh Worker processes, with CUDA determinism configured before use.

The harness records measured GPU properties and supports at most two distinct
resume IDs. Resume uses the authenticated public job interface and an existing
confirmed escrow. Real-model fingerprints must bind the exact preflight model
and input hashes. Withdrawal baseline and resumed settlement state are read at
one shared block, preventing inconsistent credit accounting.

## Sanitized evidence

- Chain: `421614` (Arbitrum Sepolia).
- Contract: `0xbD0A2f65ae2C67A313d2883cAed5029A3275a599`.
- GPU: NVIDIA GeForce RTX 3050 Laptop GPU; reported memory `4294443008` bytes.
- Runtime: PyTorch `2.5.1+cu124`, CUDA `12.4`.
- Artifact SHA-256: `7eda85e9710c4195ba150ec3eda045dff1a74f05ba2d396751c5eb43575eccf2`.
- Input SHA-256: `c47dd9465c00e9a0c8b85e9ea58d3034a0d23b9cf926113602f3460752a4eb96`.
- Result SHA-256, identical for both jobs and preflight:
  `edbf766993c176f80f88db438d8eaad36245c8b9db60dc062e81aa0bfbcf290c`.
- Restart repeatability and private artifact-download verification: passed.

| Job UUID | Journey | Escrow block |
|---|---|---|
| `6bfc877d-7357-5f0a-b05e-c85eab915ec0` | Resumed existing funded job | `322261700` |
| `9048e9df-35ed-5618-8054-6a873d89e28f` | New real-model job | `322266166` |

Escrow transaction hashes, respectively:

```text
0xc0447c97913e3745e7ce7f464511ab05ab5ac5f0189ed175c5522ae56021a702
0x8d2a32e06c70aae5832540b816a4f0f855f3ec4e5c416743c319c39209c08f1d
```

Protected local evidence:
`/home/chitrangath/.local/state/nebula-gcp/wrk003-real-model-sepolia.json`.
This contains all four ordered checkpoint hashes as well as the sanitized
journey records. Signed URLs and private keys are deliberately not copied here.

After the run, a separate read-only check confirmed both database jobs were
`completed`, both on-chain jobs were settled, and both on-chain/database
fingerprints matched the approved preflight model/input. The Worker signer had
zero ETH and all four AI-user/provider/Worker/verifier identities were distinct.

## Verification

| Check | Result |
|---|---|
| Affected backend, script/preflight and owner-wizard regression suites | 111 passed |
| Affected Worker loader, executor, image-error and configuration suites | 49 passed |
| Genuine CUDA restart-repeatability preflight | Passed |
| Hosted API/private-storage/Sepolia real-model journeys | 2 passed |
| Disposable Anvil proof/settlement suite | 12 passed |
| PostgreSQL + Anvil integration closure (two runs) | 4 passed + 4 passed |
| Ruff on changed Python files; `git diff --check` | Passed |
| Mypy on the two new preflight helpers | Passed |
| Independent standards/spec reviews | No remaining blocker-level findings |

Regression coverage includes the exact legacy withdrawal, malformed-image,
stream-close, lease-expiry, reverted-assignment, shared-block accounting, and
fingerprint-mismatch cases. The corrupt PNG, legacy withdrawal and stream-close
failures were reproduced before their fixes and passed afterward.

This is targeted regression evidence, not a claim that every repository test
passed. Broader backend mypy retains existing SQLAlchemy `Column` typing errors.
Local PostgreSQL regressions could not run: port `5433` was unavailable and the
Docker CLI reported unavailable WSL integration. Tests were not redirected to
the hosted production-like database.

## Remaining gates and operational follow-up

- The real CUDA preflight and protocol-level Anvil settlement suite pass. The
  integrated backend/Worker real-model journey passed on Arbitrum Sepolia; this
  is the authoritative public acceptance gate and is stronger than duplicating
  the same funded flow on a disposable chain.
- PostgreSQL-backed integration closure is now passing twice against the
  disposable `nebula_test` database on Docker port `55432`.
- Include these backend repairs in a separately reviewed immutable deployment
  before relying on them in persistent hosted runners. This run used laptop
  runners; it did not upgrade the Cloud Run image.
- Three earlier failed jobs (`a2064c90-29ce-58bd-8ec7-ecb611ffedc8`,
  `56bdf3be-f4fd-5067-a33d-dfd10a78a876`,
  `19609c58-62ff-54eb-884a-22d07146afbe`) exhausted their normal attempts.
  Their escrow deadlines are on 2026-10-25 UTC. Follow the ordinary timeout/refund
  flow after the actual on-chain deadlines; no early refund or artificial lease
  shortening was performed.
- A later live run may require refreshing the protected signed artifact URL.
  Its expiry does not change the approved artifact hash. Do not rerun funded
  journeys merely to reproduce this already-passing evidence.

The target-GPU/artifact unavailability notes in the earlier WRK-001/WRK-002
reports describe their historical baselines; this report supersedes those gates
for WRK-003. QA-001 still depends on FE-004, but no WRK-003 gate remains open.

## Phase 5/6 skill usage

Discovered: `solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`,
`diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`,
`improve-codebase-architecture`, `handoff`, `ask-matt`,
`setup-matt-pocock-skills`, `teach`, and `wizard`.

Applied:

1. `diagnosing-bugs`: traced protected runtime errors, reproduced concrete
   image/lease/schema/history failures, and verified each cause at its boundary.
2. `tdd`: added failing regressions and checked the corresponding fixes through
   loader, executor, scheduler, dispatcher, event-projection and probe interfaces.
3. `domain-modeling`: read `CONTEXT.md` and retained its GPU provider, Worker
   signer, lease, proof, model artifact, credit, withdrawal and settlement terms;
   no glossary or protocol-domain change was needed.
4. `code-review`: independent standards/spec agents reviewed changes against
   fixed source baseline `c0053f6c3bddae9a5a5b6202d6748328dcf768f4` and the
   WRK-003 criteria. Resume-accounting and fingerprint review findings were
   fixed and regression-tested before final acceptance of the change set.

Not applied: Solidity security (no contract edits), wizard (no new human-only
steps), research (local/runtime evidence rather than external source research),
architecture/planning/refactoring (no module redesign), and routing/setup/
teaching/handoff (not needed for this runtime repair).
