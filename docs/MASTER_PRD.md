# Nebula AI Cloud - Master MVP Product Requirements Document

**Version:** 1.0  
**Status:** Canonical implementation baseline  
**Target:** Public academic MVP  
**Team:** One developer, with occasional access to one or two NVIDIA GPU machines  
**Delivery window:** 9-10 weeks  
**Source documents:** Nebula PRD v3.0 and Nebula Development-Ready PRD v2.4

---

## 1. Document Authority

This is the single source of truth for the Nebula MVP. Where this document conflicts with `NEBULA_PRD_v3.0.md` or `DEVELOPMENT_PLAN.md`, this document wins.

The older documents remain useful as historical references:

- PRD v3.0 contains the broader product vision, personas, presentation material, and deployment ideas.
- PRD v2.4 contributes the corrected execution model, PoAE trust boundary, security controls, state machine, and gated development approach.
- The existing development plan describes the original full-scope schedule but must not be treated as the current commitment.

Changes to MVP scope must be made here before they are added to implementation tasks.

---

## 2. Executive Summary

Nebula AI Cloud is a public, blockchain-backed marketplace demonstration for AI inference on independently operated GPU nodes.

A user selects an approved model, uploads an input, and funds a testnet USDC escrow. The backend assigns the job to a registered GPU node. The worker executes inference and returns a result with Simplified Proof-of-AI-Execution (PoAE) evidence. The backend validates that evidence and authorizes the escrow contract to credit either the provider or the user.

The MVP proves one complete proposition:

> A user and an independent GPU provider can complete a paid AI inference job through a public web application, with deterministic, signed, tamper-evident execution evidence controlling testnet settlement.

The MVP is intentionally centralized in scheduling and verification. Blockchain provides escrow custody and an auditable settlement record; it does not make model execution trustless.

---

## 3. Problem Statement

AI students and developers may need occasional GPU inference without purchasing hardware or configuring a full cloud environment. GPU owners may have idle capacity but lack a simple way to accept work from unknown users and receive payment.

The difficult part is not only moving a job to a remote GPU. The platform must also bind the requested model and input to the returned output, identify the provider that submitted the result, reject tampered or replayed evidence, and settle payment exactly once.

Nebula addresses this problem as a constrained public MVP. It does not attempt general-purpose compute, arbitrary model execution, or fully decentralized verification.

---

## 4. Product Principles

1. **One complete path beats broad partial support.** ResNet50 is the only required model.
2. **PoAE is the product differentiator.** A job is not complete until its evidence is verified and settlement is confirmed.
3. **Claims must match guarantees.** PoAE is signed execution evidence, not a mathematical proof of correct inference.
4. **The backend is deliberately trusted.** Central scheduling and verification are acceptable and disclosed for the MVP.
5. **Testnet only.** No real-value payments or mainnet launch are permitted.
6. **Private by default.** Inputs and results are not published to IPFS or public object storage.
7. **Every external operation is retryable or reconcilable.** Network retries must not create duplicate jobs, proofs, payments, or refunds.
8. **Stretch work cannot block launch.** Additional models and infrastructure begin only after the required launch gate passes.

---

## 5. Target Users

### AI user

A student or developer who wants to run a supported inference job from a browser and inspect the result, execution evidence, and testnet settlement.

### GPU provider

A person operating a Linux machine with a supported NVIDIA GPU who wants to register one node, run the Nebula worker, process jobs, and receive testnet earnings.

### Evaluator

A faculty member, reviewer, or technical observer who wants to see a reproducible end-to-end demonstration and understand exactly what PoAE does and does not guarantee.

---

## 6. MVP Scope

### Required

- Public React web application.
- MetaMask wallet connection and wallet-signature login.
- One approved model: ResNet50 image classification.
- JPEG and PNG inputs up to 10 MB.
- One job at a time per GPU node.
- Linux worker with NVIDIA CUDA support.
- At least one independently operated worker; two workers for the final demonstration if hardware is available.
- Private Cloudflare R2 storage for model artifact, input, result, and proof envelope.
- PostgreSQL for application data, queue state, leases, and auth challenges.
- Arbitrum Sepolia escrow using a documented test token.
- Deterministic PoAE fingerprint, fixed checkpoints, Merkle root, result hash, and worker signature.
- Backend proof verification before provider credit or user refund.
- User job list, job detail, result download, PoAE status, and explorer link.
- Provider node registration, node status, current job, and earnings view.
- Polling for dashboard updates.
- Timeout, retry, refund, and chain/database reconciliation paths.
- Automated tests and a reproducible public demo.

### Stretch, only after the launch gate passes

- A second model, preferably YOLOv5.
- More than two concurrent workers.
- Redis or Upstash queueing.
- WebSocket updates.
- IPFS publication for explicit non-sensitive demo outputs.
- Worker installer or setup wizard.
- Windows or macOS worker support.
- BERT Base and Whisper Tiny.
- Notifications, reputation, dynamic pricing, or richer analytics.

### Explicitly out of scope

- Mainnet or real-value payments.
- Arbitrary model uploads or arbitrary code execution.
- Model training, fine-tuning, AutoML, or datasets.
- Fully decentralized scheduling or verification.
- Zero-knowledge proofs, trusted execution environments, staking, slashing, or disputes.
- Confidential inference or protection from a provider viewing plaintext data.
- High availability, autoscaling guarantees, or an SLA.
- Kubernetes or multi-region infrastructure.
- A token economy.
- Permanent public storage by default.

---

## 7. Success Criteria

The MVP is ready for demonstration when all required criteria pass:

| Area | Required result |
|---|---|
| End-to-end flow | 10 consecutive ResNet50 jobs complete successfully |
| Workers | At least one external Linux/NVIDIA worker completes jobs |
| Multiple nodes | Two workers complete and receive separate jobs if hardware is available |
| PoAE integrity | 100% of defined tampered proof cases are rejected |
| Replay protection | Cross-job, cross-lease, cross-contract, and cross-chain replays fail |
| Settlement | No duplicate provider credit or refund in tests |
| Recovery | A killed worker lease expires and the job is retried or refunded |
| Privacy | Unauthorized users cannot download another user's input, result, or proof |
| Reconciliation | Contract and database recover after a simulated dropped transaction |
| Usability | A new user and provider complete the documented flow without code changes |

Performance goals are modest and are not service-level guarantees:

- API p95 below 750 ms excluding files, inference, and blockchain confirmation.
- Dashboard state visible within 5 seconds through polling.
- Two simultaneous jobs supported when two workers are online.

---

## 8. Canonical Language

| Term | Definition |
|---|---|
| **Job** | One request to run one approved model version against one exact input for one fixed testnet price |
| **GPU provider** | Wallet-identified participant that operates one or more nodes |
| **GPU node** | Provider-operated machine registered to receive jobs |
| **Worker** | Nebula software process running on a GPU node |
| **Lease** | Time-bounded exclusive assignment of a job to one node |
| **Job fingerprint** | Deterministic hash binding protocol, model artifact, preprocessing version, and input |
| **Checkpoint** | Named model-specific point whose intermediate tensor is hashed |
| **Execution trace** | Ordered checkpoint names and hashes for one inference |
| **Proof envelope** | Versioned signed package containing PoAE evidence and job-binding metadata |
| **PoAE proof** | User-facing name for the proof envelope; not a zero-knowledge proof |
| **Verifier** | Trusted backend role that validates proof envelopes |
| **Verdict** | Terminal `VALID` or `INVALID` proof decision |
| **Settlement** | Single escrow outcome crediting either provider earnings or a user refund |

The terms node, worker, and provider are not interchangeable.

---

## 9. User Stories

1. As an AI user, I want to sign in with MetaMask so that I do not need a password.
2. As an AI user, I want to see the supported model, input rules, fixed price, and testnet label before submitting a job.
3. As an AI user, I want to upload a valid image directly to private storage so that large files do not pass through the API process.
4. As an AI user, I want invalid formats and oversized files rejected before payment.
5. As an AI user, I want to approve and fund the exact fixed testnet price through MetaMask.
6. As an AI user, I want scheduling to begin only after the escrow event is confirmed.
7. As an AI user, I want to see whether my job is awaiting escrow, queued, running, verifying, settling, completed, or refunded.
8. As an AI user, I want to download my result through an expiring private URL.
9. As an AI user, I want to inspect the fingerprint, Merkle root, output hash, provider, verdict, and settlement transaction.
10. As an AI user, I want an expired or repeatedly failed job refunded exactly once.
11. As a GPU provider, I want to register a node and authorize a separate worker signing key without placing my wallet private key on the worker.
12. As a GPU provider, I want a revocable node credential so that a leaked credential can be disabled.
13. As a GPU provider, I want my worker to reject modified models or inputs before inference.
14. As a GPU provider, I want only jobs compatible with my node assigned to me.
15. As a GPU provider, I want a lease to prevent two workers from processing the same attempt.
16. As a GPU provider, I want my worker to resume polling after network interruption.
17. As a GPU provider, I want valid work to become withdrawable testnet earnings.
18. As an evaluator, I want a clear disclosure of the centralized verifier so that I can assess the innovation honestly.
19. As an evaluator, I want tampering and replay demonstrations so that PoAE behavior is observable rather than asserted.
20. As an operator, I want contract/database reconciliation so that dropped RPC responses do not corrupt job state.
21. As an operator, I want secrets and private URLs excluded from logs.
22. As an operator, I want health checks and a short runbook so that the demo can be recovered quickly.

---

## 10. Canonical Architecture

| Layer | MVP technology | Responsibility |
|---|---|---|
| Frontend | React, TypeScript, Vite, Vercel | Wallet login, submission, dashboards |
| Backend | FastAPI, OCI Always Free Ampere VM | API, scheduling, verification, settlement orchestration |
| Database | PostgreSQL, Supabase | Workflow state, leases, proof audit, auth challenges |
| Object storage | Private Cloudflare R2 | Model, input, result, proof envelope |
| Blockchain | Arbitrum Sepolia | Escrow custody and settlement events |
| Contract tooling | Solidity 0.8.20, Foundry, pinned OpenZeppelin | Escrow implementation and tests |
| Worker | Python, PyTorch, CUDA | ResNet50 inference and PoAE generation |

Redis, IPFS, WebSockets, and notification services are not required MVP dependencies.

### Source-of-truth boundaries

- PostgreSQL is authoritative for application workflow and lease state.
- The contract is authoritative for escrow balance and settlement state.
- R2 is authoritative for retained model, input, result, and proof objects.
- The backend reconciles PostgreSQL against confirmed contract events.

### Environments

- Local development uses local PostgreSQL and S3-compatible storage where practical.
- Staging uses the same service types as production and the same Arbitrum Sepolia contract interface.
- Production is still an MVP testnet environment, not a mainnet environment.
- All URLs come from environment variables; custom domains are optional.

---

## 11. Job and Settlement Model

### Identifiers

- `job_id` is a PostgreSQL UUID used by API routes and foreign keys.
- `chain_job_id` is `keccak256` of the canonical lowercase UUID string and is stored as `bytes32` on-chain.
- UUID strings must never be truncated into `bytes32`.
- The backend stores both values and verifies their mapping whenever it processes an event.

### Job state machine

```text
UPLOADING -> AWAITING_ESCROW -> QUEUED -> LEASED -> RUNNING
RUNNING -> VERIFYING -> SETTLING -> COMPLETED
LEASED/RUNNING -> QUEUED                    retryable attempt failure
QUEUED/LEASED/RUNNING/VERIFYING -> REFUNDING -> REFUNDED
UPLOADING/AWAITING_ESCROW -> CANCELLED      pre-escrow expiry only
```

`COMPLETED`, `REFUNDED`, and `CANCELLED` are terminal. All transitions are enforced by one backend workflow service inside database transactions.

### Scheduling

- The database is the MVP queue.
- The scheduler assigns the oldest eligible queued job.
- Assignment uses row locking so only one active lease can exist for a job.
- A worker acknowledges a lease before receiving download URLs.
- A lease has an expiry and heartbeat-based extension.
- A failed or expired attempt is retried once on another eligible node when available.
- After the retry budget is exhausted, the job is refunded.

---

## 12. Simplified Proof-of-AI-Execution

### Security claim

PoAE provides tamper-evident, worker-signed execution evidence that the trusted Nebula backend validates before settlement. It binds the registered model artifact and exact input to an ordered checkpoint commitment and result hash.

PoAE does not prove correct inference against a malicious custom worker. The worker can fabricate internally consistent hashes, and the centralized verifier can authorize an incorrect verdict. Product copy must not say cheating is cryptographically impossible or call the MVP fully trustless.

### Step 1 - Deterministic fingerprint

The backend computes the fingerprint before escrow creation, and the worker independently recomputes it before inference:

```text
fingerprint = SHA256(
  "nebula-job-v1" ||
  model_id ||
  model_version ||
  model_artifact_sha256 ||
  preprocessing_version ||
  input_sha256
)
```

The encoding is documented and covered by fixed test vectors. Current date, local time, pickle output, and runtime object serialization are forbidden inputs.

### Step 2 - Fixed ResNet50 checkpoints

The ResNet50 adapter defines three or four named checkpoints in code and protocol documentation. It does not discover checkpoints using `model.children()` at runtime.

Each checkpoint hash binds:

- PoAE protocol version.
- Checkpoint index and name.
- Tensor data type and shape.
- Canonical contiguous tensor bytes.

Model evaluation mode, preprocessing version, dependency versions, and numeric precision are recorded in the proof envelope.

### Step 3 - Output and Merkle commitment

The result uses one canonical JSON schema for ResNet50 classifications. `output_hash` is computed from canonical UTF-8 JSON bytes, not Python pickle.

Merkle leaves are the ordered checkpoint hashes followed by the output hash. Leaf prefixing, parent prefixing, byte encoding, and odd-leaf handling are explicitly specified and shared through golden test vectors.

### Step 4 - Worker signature

Worker setup generates a separate secp256k1 signing key. The provider authorizes its public address for one node using the provider wallet. The provider wallet private key never enters worker configuration.

The proof uses an EIP-712 typed-data signature that binds:

- Protocol version.
- Database and on-chain job IDs.
- Lease ID.
- Chain ID and escrow contract address.
- Fingerprint, Merkle root, and output hash.
- Authorized worker signer and provider wallet.
- Issued and expiry times.

### Step 5 - Backend verdict

The verifier checks, in order:

1. Schema and supported protocol version.
2. Job state and active lease ownership.
3. Lease and proof freshness.
4. Fingerprint against trusted model and input hashes.
5. Required checkpoint names, order, count, and encoding.
6. Rebuilt Merkle root.
7. Uploaded canonical result against `output_hash`.
8. EIP-712 signer against the node's authorized worker signer.
9. Replay and prior-verdict status.

The verifier stores each check and one final verdict before enqueueing settlement. Verification and settlement are idempotent.

### Failure behavior

| Failure | Outcome |
|---|---|
| Worker disconnect before proof | Lease expires; retry once |
| Model/input fingerprint mismatch | Attempt rejected; security event recorded |
| Malformed, tampered, stale, or replayed proof | `INVALID`; user refund |
| Signature mismatch | `INVALID`; node disabled pending review |
| Temporary backend, R2, or RPC failure | Remain non-terminal and retry idempotently |
| No successful attempt before escrow deadline | User refund |

### User-visible evidence

The job detail view shows PoAE status, shortened fingerprint, Merkle root, output hash, provider wallet, checkpoint count, verifier timestamp, and settlement transaction. It also displays the centralized-verifier disclosure.

---

## 13. Escrow Contract Requirements

The canonical contract may retain the existing project name `NebulaVerifiableAI`, but its MVP behavior is:

- `createJob(chainJobId, fingerprint)` escrows the contract-configured fixed price.
- Duplicate or zero IDs and fingerprints revert.
- Only the configured verifier can submit a final valid or invalid settlement.
- A valid settlement records provider, Merkle root, and output hash and credits provider withdrawal balance.
- An invalid settlement credits user refund balance.
- A user can trigger refund after an objective job deadline if no verdict exists.
- Each job reaches exactly one terminal settlement.
- Withdrawals use pull payments and checks-effects-interactions.
- ERC-20 transfers use `SafeERC20`.
- Owner and verifier changes emit events.
- A maximum job price and pause mechanism limit testnet operational risk.

Workers do not call the contract. The contract does not verify the complete proof envelope; the trusted backend does that off-chain.

Required contract invariants:

- Total escrow received equals pending escrow plus unclaimed provider credit plus unclaimed user refunds plus completed withdrawals.
- A job cannot be settled twice.
- An unauthorized address cannot settle, redirect, or withdraw another account's balance.
- A timed-out job cannot later pay a provider.
- Reentrant token behavior cannot duplicate settlement or withdrawal.

---

## 14. Functional Requirements

### Authentication

- MetaMask is the only required wallet connector.
- Challenge contains domain, wallet, chain ID, nonce, issue time, and expiry.
- Challenge is single-use and stored hashed in PostgreSQL.
- Successful verification creates a short-lived secure session.
- Logout revokes the session.
- Wallet address comparison uses normalized addresses.

### Model registry

- Only ResNet50 is enabled for the required MVP.
- Registry contains immutable artifact hash, model version, preprocessing version, VRAM requirement, input policy, timeout, and fixed token price.
- Placeholder artifact hashes are forbidden outside local development.
- Worker refuses an artifact hash mismatch.

### Input and storage

- JPEG and PNG only, detected by content and decoded before acceptance.
- Maximum input is 10 MB.
- Frontend requests an upload slot and uploads directly to private R2.
- Backend validates the stored object and computes `input_sha256` before job creation.
- Signed download URLs expire within five minutes.
- Inputs expire after 24 hours; results and proof envelopes after seven days.
- Storage keys, not signed URLs, are persisted in PostgreSQL.

### Node management

- Provider registers GPU name, VRAM, CUDA capability, and region label.
- Node receives a one-time credential; only its hash is stored.
- Credential can be rotated and revoked.
- Worker signer authorization is linked to provider, node, and signer address.
- Worker heartbeats every 30 seconds; node becomes offline after 90 seconds.

### Worker

- Linux and NVIDIA CUDA are required.
- Worker processes one active lease at a time.
- HTTP requests use explicit connect/read timeouts and bounded exponential backoff.
- Model and input hashes are verified before execution.
- Inference runs in evaluation mode with a hard timeout.
- Result serialization and PoAE generation are deterministic.
- Worker never receives backend verifier credentials or R2 master credentials.

### Dashboards

User interface:

- Wallet login.
- ResNet50 submission with preview, validation, price, and testnet label.
- Job list and status timeline.
- Result download and top classifications.
- PoAE evidence summary and settlement/refund explorer link.

Provider interface:

- Node registration and one-time credential display.
- Worker signer authorization instructions.
- Online/offline status and last heartbeat.
- Current lease and completed job history.
- Credited and withdrawn testnet earnings.

Polling every three to five seconds is sufficient. No WebSocket dependency is required.

---

## 15. Minimal API Surface

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/v1/auth/challenge` | Create wallet challenge |
| `POST` | `/v1/auth/verify` | Verify wallet and start session |
| `POST` | `/v1/auth/logout` | Revoke session |
| `GET` | `/v1/models` | Return enabled ResNet50 configuration |
| `POST` | `/v1/jobs/upload` | Create private input upload slot |
| `POST` | `/v1/jobs` | Validate upload and create pre-escrow job |
| `POST` | `/v1/jobs/{id}/confirm-escrow` | Confirm and validate contract event |
| `GET` | `/v1/jobs` | List user's jobs |
| `GET` | `/v1/jobs/{id}` | Return job, PoAE, and settlement state |
| `GET` | `/v1/jobs/{id}/result-url` | Return authorized result download URL |
| `POST` | `/v1/nodes` | Register provider node |
| `POST` | `/v1/nodes/{id}/credentials/rotate` | Rotate node credential |
| `GET` | `/v1/providers/me` | Provider nodes and earnings |
| `POST` | `/v1/worker/heartbeat` | Update node health |
| `POST` | `/v1/worker/leases/next` | Acquire next compatible lease |
| `POST` | `/v1/worker/leases/{id}/ack` | Acknowledge lease |
| `POST` | `/v1/worker/leases/{id}/result-upload` | Create result upload slot |
| `POST` | `/v1/worker/leases/{id}/complete` | Submit result metadata and proof envelope |
| `POST` | `/v1/worker/leases/{id}/fail` | Report attempt failure |
| `GET` | `/v1/health/live` | Process liveness |
| `GET` | `/v1/health/ready` | Dependency readiness |

Mutating retryable endpoints require idempotency keys. Job and object endpoints enforce ownership rather than relying on UUID secrecy.

---

## 16. Data Model

| Table | Required responsibility |
|---|---|
| `users` | Normalized wallet identity |
| `auth_challenges` | Single-use wallet login nonces |
| `sessions` | Hashed revocable session tokens |
| `supported_models` | One immutable enabled ResNet50 configuration |
| `nodes` | Provider ownership, credential hash, signer, hardware, heartbeat |
| `jobs` | User, model, storage keys, hashes, IDs, price, state, retries, timestamps |
| `job_attempts` | Node lease, acknowledgement, expiry, outcome |
| `proofs` | Versioned envelope, individual checks, verdict, failure reason |
| `chain_transactions` | Escrow/settlement/refund transaction and confirmation state |

Monetary values use integer token base units. Timestamps are timezone-aware UTC. States are constrained enums. Chain job IDs and transaction hashes are unique where present.

---

## 17. Testing Decisions

The primary testing seam is the complete job lifecycle through the backend workflow service. External storage, chain, and worker execution use fakes in fast tests and real staging dependencies in a small end-to-end suite.

### Required automated tests

- Contract unit, fuzz, and invariant tests for every authorization and fund-moving path.
- Shared PoAE golden vectors consumed by fingerprint, checkpoint, Merkle, result, signature, and verifier tests.
- Backend state-transition tests, including invalid transitions and duplicate requests.
- Scheduler tests for eligibility, row locking, lease expiry, retry, and exhaustion.
- Authorization tests proving users cannot read or mutate another user's resources.
- Worker tests using fixed images and a pinned ResNet50 artifact.
- Integration tests for PostgreSQL transactions and signed R2 URLs.
- Testnet contract event ingestion and reconciliation tests.
- End-to-end success, invalid proof, worker crash, refund, verifier restart, and dropped-RPC scenarios.

Tests assert externally observable behavior. They do not depend on private helper structure or exact log text.

### Required PoAE tamper cases

- Changed model artifact hash.
- Changed input hash.
- Missing, additional, reordered, or modified checkpoint.
- Changed output bytes.
- Wrong worker signer or provider.
- Expired proof.
- Reused lease.
- Reused proof on another job, contract, or chain.
- Duplicate valid verdict.
- Valid verdict after timeout refund.

### Manual checks

- MetaMask approval and transaction states.
- Mobile and desktop dashboard layouts.
- New-provider setup on a clean Linux machine.
- R2 retention and signed URL expiry.
- Explorer links and testnet labeling.
- Recovery using the operator runbook.

---

## 18. Delivery Plan

Each phase has a gate. The next phase does not become the active commitment until the current gate passes.

### Phase 0 - Reset the baseline (Days 1-2)

**Deliverables:**

- Adopt this document as canonical.
- Update implementation tasks to remove stretch scope.
- Record fixed formats for job IDs, fingerprint, result JSON, Merkle tree, and EIP-712 proof.
- Pin Solidity, OpenZeppelin, Python, PyTorch, Node, and frontend dependencies.
- Preserve existing useful scaffolding; identify code that must be replaced.

**Gate:** One documented golden PoAE vector exists, contract interface is agreed, and no task still treats Redis, IPFS, four models, or cross-platform workers as required.

### Phase 1 - Correct escrow contract (Week 1)

**Deliverables:**

- Replace worker `submitProof` plus `verifyJob` with verifier-only terminal settlement.
- Fixed contract price, timeout refund, pull balances, pause control, and event model.
- Foundry unit, fuzz, invariant, authorization, timeout, and reentrancy tests.
- Local deployment script and test token.

**Gate:** All fund-moving branches pass; escrow conservation invariant passes; unauthorized settlement and duplicate settlement fail.

### Phase 2 - Backend workflow foundation (Weeks 2-3)

**Deliverables:**

- Database migrations and constrained job state machine.
- Wallet auth and revocable node credentials.
- Private R2 upload/download and retention behavior.
- ResNet50 registry entry with real artifact and preprocessing hashes.
- Escrow confirmation and contract event reconciliation.
- Database-backed scheduler and leases.

**Gate:** A test creates, escrows, queues, leases, expires, retries, and refunds a job without frontend or real inference.

### Phase 3 - Worker and PoAE vertical slice (Weeks 4-5)

**Deliverables:**

- Linux/NVIDIA worker polling and heartbeat.
- ResNet50 model loader, fixed preprocessing, inference adapter, and canonical result.
- Deterministic fingerprint, fixed checkpoints, Merkle tree, and EIP-712 signer.
- Proof verifier and idempotent settlement worker.

**Gate:** Ten golden jobs produce expected proof commitments; every required tamper vector fails; one real GPU job settles correctly on local chain and Arbitrum Sepolia staging.

### Phase 4 - Thin usable frontend (Week 6)

**Deliverables:**

- MetaMask authentication.
- User submission, escrow, job list, result, PoAE, and refund views.
- Provider registration, node status, and earnings views.
- Polling and complete loading/error/transaction states.

**Gate:** A new user and provider can complete the happy path using only documented setup instructions.

### Phase 5 - Failure handling and integration (Weeks 7-8)

**Deliverables:**

- Worker death, lease timeout, retry, invalid proof, refund, backend restart, and RPC recovery flows.
- Ownership, rate-limit, upload, credential-revocation, and secret-leakage tests.
- Contract/database reconciliation command and operator runbook.
- CI for contract, backend, worker, frontend, migrations, and end-to-end tests.

**Gate:** All launch success criteria pass in staging with no open critical or high-severity defect.

### Phase 6 - Public MVP and evaluation (Weeks 9-10)

**Deliverables:**

- Vercel frontend, OCI Always Free backend, Supabase PostgreSQL, private R2, and Arbitrum Sepolia deployment.
- Monitoring, readiness checks, structured logs, backup/restore check, and smoke test.
- Public README, worker guide, architecture diagram, PoAE limitations, and demonstration script.
- Small beta with at least five users and one external provider.

**Gate:** Ten consecutive public jobs complete, tamper/refund demo succeeds, contract and database reconcile, and a new participant completes the documented flow without developer intervention.

### Post-gate stretch sequence

1. Add a second GPU worker and demonstrate parallel leases.
2. Add YOLOv5 through a complete model-specific adapter and golden vectors.
3. Add optional IPFS publication for explicit non-sensitive results.
4. Add Redis only when measured database queue contention justifies it.
5. Add WebSockets only when polling creates a measured user or capacity problem.
6. Evaluate BERT, Whisper, Windows, and macOS independently; none are automatic commitments.

---

## 19. Current Repository Assessment

The repository already contains useful scaffolding for contracts, backend configuration, database migration, frontend routes, and worker modules. It is not yet an end-to-end MVP.

The following existing choices must be replaced before building further features:

- Date- and pickle-dependent fingerprint computation.
- Dynamic `model.children()` tracing and skipped-trace placeholders.
- Plain-text EIP-191 message construction with inconsistent timestamps.
- Worker wallet private key configuration.
- Worker/owner `submitProof` contract flow.
- Immediate token transfers without timeout-safe pull balances.
- Client-provided escrow amount.
- Four placeholder model records and hashes.
- Public R2/IPFS result publication as a default.
- Unconstrained string job statuses and decimal token accounting.

Existing contract tests are a useful starting point but validate the old contract behavior. They must be rewritten around the canonical contract invariants in this document.

---

## 20. Risks and Mitigations

| Risk | Practical mitigation |
|---|---|
| PoAE is mistaken for full correctness proof | Precise disclosure in PRD, UI, README, and demo |
| Model checkpoints differ across runtime versions | Pin artifact/runtime and use named adapter plus golden vectors |
| GPU access is unreliable | Require one external worker; treat second as demonstration target |
| Test token or faucet is unavailable | Keep a local mock token and document the selected staging token |
| Contract traps funds | Timeout refund, pull balances, invariant tests, testnet only |
| Backend and chain diverge | Confirmed event processing and reconciliation command |
| User data becomes public | Private R2, expiring URLs, no default IPFS |
| One developer runs out of time | One model, one platform, polling, database queue, hard stretch boundary |
| Hosting free tiers change | Verify quotas before deployment; custom domains remain optional |

---

## 21. Launch Checklist

- [ ] Master PRD is the active scope reference.
- [ ] ResNet50 artifact and preprocessing hashes are real and pinned.
- [ ] Contract address, chain ID, and test token are verified independently.
- [ ] Every UI payment is clearly labeled testnet.
- [ ] No provider wallet private key is stored on a worker.
- [ ] PoAE golden and tamper vectors pass.
- [ ] Timeout refund and duplicate-settlement tests pass.
- [ ] Cross-user object access tests pass.
- [ ] Worker crash and backend restart recovery pass.
- [ ] Contract and PostgreSQL reconciliation reports no mismatch.
- [ ] Input and result retention behavior is confirmed.
- [ ] Monitoring and readiness checks are active.
- [ ] Operator and worker setup guides are tested from a clean environment.
- [ ] No critical or high-severity defect remains open.
- [ ] Public end-to-end demonstration succeeds.

---

## 22. Final MVP Definition

Nebula MVP is complete when a user can fund one ResNet50 inference job, an independently operated Linux/NVIDIA worker can execute it and produce valid PoAE evidence, the trusted backend can verify that evidence, and the Arbitrum Sepolia contract can settle exactly once to the provider or refund the user after failure.

Everything beyond that sentence is either support for making the flow reliable or post-MVP scope.
