# Nebula AI Cloud — Canonical MVP Product Requirements Document

## Version 3.1

**Status:** Canonical specification — supersedes NEBULA_PRD_v3.0.md, MASTER_PRD.md, and PRD v2.3
**Date:** September 2026
**Target:** Public academic MVP
**Team:** 1–4 students
**Budget:** $0 (free-tier services only)
**Delivery window:** 12 weeks

---

## Table of Contents

1. [Document Control](#1-document-control)
2. [Executive Summary](#2-executive-summary)
3. [Product Scope and Non-Goals](#3-product-scope-and-non-goals)
4. [Trust Model and Security Claims](#4-trust-model-and-security-claims)
5. [Users and Core Flows](#5-users-and-core-flows)
6. [System Architecture](#6-system-architecture)
7. [Canonical Identifiers and Encoding](#7-canonical-identifiers-and-encoding)
8. [Deterministic Fingerprint Protocol](#8-deterministic-fingerprint-protocol)
9. [PoAE Proof Envelope and Verification](#9-poae-proof-envelope-and-verification)
10. [Job, Attempt, and Lease State Machines](#10-job-attempt-and-lease-state-machines)
11. [Smart Contract Specification](#11-smart-contract-specification)
12. [Payment, Withdrawal, and Refund Accounting](#12-payment-withdrawal-and-refund-accounting)
13. [Backend Services](#13-backend-services)
14. [Worker Architecture](#14-worker-architecture)
15. [Database Schema](#15-database-schema)
16. [API Contract](#16-api-contract)
17. [Storage Architecture](#17-storage-architecture)
18. [Authentication and Authorization](#18-authentication-and-authorization)
19. [Blockchain Event Processing and Reconciliation](#19-blockchain-event-processing-and-reconciliation)
20. [Dashboard Requirements](#20-dashboard-requirements)
21. [Testing and Security Invariants](#21-testing-and-security-invariants)
22. [Deployment Architecture](#22-deployment-architecture)
23. [MVP Roadmap](#23-mvp-roadmap)
24. [Known Limitations](#24-known-limitations)
25. [Post-MVP Work](#25-post-mvp-work)
26. [Acceptance Criteria](#26-acceptance-criteria)
27. [Migration Notes from v3.0](#27-migration-notes-from-v30)
28. [Decision Log](#28-decision-log)
29. [Glossary](#29-glossary)

---

## 1. Document Control

| Field | Value |
|---|---|
| Document title | Nebula AI Cloud — Canonical MVP PRD |
| Version | 3.1 |
| Supersedes | NEBULA_PRD_v3.0.md, MASTER_PRD.md, PRD v2.3 |
| Historical references | NEBULA_PRD_v3.0.md (broader product vision), MASTER_PRD.md (security hardening), PRD v2.3 (PoAE innovation framing) |
| Canonical status | This document is the single source of truth for the MVP. Where it conflicts with any earlier document, this document wins. |
| Changes to scope | Must be recorded in the Decision Log (Section 28) before implementation. |

Older documents remain useful as historical references but must not be treated as the current commitment.

---

## 2. Executive Summary

Nebula AI Cloud is a public, blockchain-backed marketplace demonstration for AI inference on independently operated GPU nodes.

A user selects an approved model, uploads an input, and funds a testnet USDC escrow. The backend assigns the job to a registered GPU node. The worker executes inference and returns a result with Simplified Proof-of-AI-Execution (PoAE) evidence. The backend validates that evidence and authorizes the escrow contract to credit either the provider or the user.

The MVP proves one complete proposition:

> A user and an independent GPU provider can complete a paid AI inference job through a public web application, with deterministic, signed, tamper-evident execution evidence controlling testnet settlement.

The MVP is intentionally centralized in scheduling and verification. Blockchain provides escrow custody and an auditable settlement record; it does not make model execution trustless.

**Honest PoAE claim:** PoAE provides tamper-evident, worker-signed execution evidence that the trusted Nebula backend validates before settlement. It binds the registered model artifact and exact input to an ordered checkpoint commitment and result hash. PoAE does not prove correct inference against a malicious custom worker. The worker can fabricate internally consistent hashes, and the centralized verifier can authorize an incorrect verdict. Product copy must not say cheating is cryptographically impossible or call the MVP fully trustless.

---

## 3. Product Scope and Non-Goals

### 3.1 Required MVP

- Public React web application on Vercel.
- MetaMask wallet connection and wallet-signature login.
- Four approved models: ResNet50 (primary), YOLOv5, BERT-Base, Whisper Tiny.
- Input validation per model (JPEG/PNG for vision, TXT for text, WAV/MP3 for audio).
- One job at a time per GPU node.
- Linux worker with NVIDIA CUDA support required. Windows and macOS are stretch.
- At least one independently operated worker; two for the final demonstration if hardware is available.
- Private Cloudflare R2 storage for model artifacts, inputs, results, and proof envelopes.
- PostgreSQL for application data, queue state, leases, and auth challenges.
- Arbitrum Sepolia escrow using a documented test token (Circle USDC).
- Deterministic PoAE fingerprint, fixed checkpoints, Merkle root, result hash, and worker EIP-712 signature.
- Backend proof verification before provider credit or user refund.
- User job list, job detail, result download, PoAE status, and explorer link.
- Provider node registration, node status, current job, and earnings view.
- Polling for dashboard updates (5–10 second interval). No WebSocket dependency.
- Timeout, retry, refund, and chain/database reconciliation paths.
- Pull-payment settlement with permissionless `withdraw()`.
- Emergency pause without trapping user funds.
- Automated tests and a reproducible public demo.

### 3.2 Stretch (only after the launch gate passes)

- Optional IPFS publication for explicit non-sensitive demo outputs.
- A second GPU worker and parallel lease demonstration.
- Redis or Upstash queueing if measured database contention justifies it.
- WebSocket updates only when polling creates a measured user or capacity problem.
- Worker installer or setup wizard.
- Windows or macOS worker support.
- Notifications (Discord/Telegram).
- Reputation, dynamic pricing, or richer analytics.
- Mainnet withdrawal.

### 3.3 Explicitly Out of Scope

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

## 4. Trust Model and Security Claims

### 4.1 Trust Boundaries

| Component | Trust Assumption | Risk | Mitigation | Why Acceptable |
|---|---|---|---|---|
| **Backend** | Correctly calls verifyJob and assignProvider | HIGH: Could lie about completion or assign wrong provider | Smart contract checks state transitions, pull payments, timeout refund | MVP: We control backend; contract enforces invariants |
| **Smart Contract** | USDC is the real Circle testnet token | LOW: Could interact with fake token | Verify address on Arbitrum Sepolia explorer before deployment | Blockchain-verified |
| **Worker API Key** | Only providers use their key | MEDIUM: Could leak or share | Revocable keys, rate limiting, TLS required | Auto-generated, can revoke instantly |
| **Model Downloads** | Pre-vetted registry only | LOW: Prevents code execution | No arbitrary uploads + SHA-256 hash verification | Restricted scope |
| **Input Files** | Only legitimate users upload | MEDIUM: Could upload malware | MIME scan, size limits, auto-delete after 24 hours | Files deleted after retention |
| **Results / IPFS** | Stored on R2 (private) and optionally IPFS (permanent) | LOW: IPFS data is immutable | Users informed before optional IPFS publication | Opt-in only |
| **Frontend** | User's wallet is secure | LOW: MetaMask is standard | Users responsible for key security | Industry standard |
| **Database** | Supabase not breached | MEDIUM: Cloud provider risk | Strong passwords, 2FA, encrypted at rest | Standard cloud practice |
| **R2 Credentials** | API key not leaked | MEDIUM: Could be stolen | Rotate keys regularly, audit logs | Monitor R2 access |
| **JWT Token** | Only user can use | MEDIUM: Could be stolen | 24h access, 7d refresh, httpOnly cookie, rotation, reuse detection | Short-lived, revocable |

### 4.2 PoAE Security Claim (Honest Disclosure)

PoAE provides tamper-evident, worker-signed execution evidence that the trusted Nebula backend validates before settlement. The guarantee is:

- **Proves:** The assigned provider submitted a signed proof envelope containing a deterministic fingerprint, ordered checkpoint hashes, a Merkle root commitment, and an output hash, all bound to a specific job, lease, and model artifact.
- **Does not prove:** That a physical GPU performed the inference. The worker can fabricate internally consistent hashes, and the centralized backend verifier can authorize an incorrect verdict.
- **MVP trust model:** The backend is trusted. PoAE provides an audit trail and tamper-evidence, not trustless verification.

### 4.3 Post-MVP Verification Enhancements

The following stronger verification mechanisms are explicitly deferred:

- Replicated execution across multiple workers.
- Randomized verifier challenges.
- Trusted execution environment (TEE) attestation.
- Optimistic disputes with fraud proofs.
- Zero-knowledge machine learning (ZKML) proofs.
- Multiple independent verifier network.
- Staking and slashing.
- On-chain ECDSA or EIP-1271 signature verification (gas too high on testnet).

---

## 5. Users and Core Flows

### 5.1 User Roles

| Role | Description |
|---|---|
| **AI User** | Wallet-identified participant that submits and funds inference jobs. |
| **GPU Provider** | Wallet-identified participant that operates one or more GPU nodes and may earn testnet payment for valid jobs. |
| **Evaluator** | Faculty member, reviewer, or technical observer who inspects the end-to-end demonstration. |

### 5.2 Flow 1: GPU Provider Registers

```
Provider (at home with GPU machine):
  1. Open Nebula app
  2. Click "Register as Provider"
  3. Connect wallet (MetaMask)
  4. Fill form: GPU name, VRAM, location
  5. Click "Register Node"
  6. Backend creates UUID node record (status: "pending")
  7. Backend generates one-time API credential, stores only hash
  8. Provider receives node_id + API key (displayed once)
  9. Download worker script
  10. Follow setup instructions (Linux required, Windows/Mac stretch)
  11. Configure worker: node_id, API key, backend_url, worker_signing_key
  12. Run: python worker.py
  13. Dashboard shows "Node Online" (heartbeat every 30s)
  14. Ready to receive jobs
```

### 5.3 Flow 2: User Submits Job

```
User:
  1. Open app, connect wallet (MetaMask)
  2. Click "Submit Job"
  3. Select model from dropdown (YOLOv5 / BERT-Base / ResNet50 / Whisper Tiny)
  4. Upload input file (drag-drop, size validated per model)
  5. See fixed cost and testnet label
  6. Click "Submit & Pay"

Platform (automatic):
  7. Frontend requests input upload slot → POST /v1/jobs/upload
  8. Backend creates presigned R2 upload URL (5min expiry)
  9. Frontend uploads input directly to R2
  10. Frontend calls POST /v1/jobs with model_id + input reference
  11. Backend computes input SHA-256, creates UUID job record (status: pending_blockchain)
  12. Backend computes expected fingerprint deterministically
  13. Backend returns {job_id, chain_job_id, model_id, amount, expected_fingerprint}
  14. Frontend calls smart contract createJob(chain_job_id, fingerprint) via MetaMask
  15. Smart contract escrows USDC
  16. Frontend calls POST /v1/jobs/{id}/confirm-escrow with tx_hash
  17. Backend verifies on-chain escrow event, updates status → queued
  18. Scheduler picks eligible node, calls assignProvider on contract
  19. Job status → assigned, lease created

Worker:
  20. Worker polls POST /v1/worker/leases/next
  21. Worker receives lease with job details, signed download URLs
  22. Worker calls POST /v1/worker/leases/{id}/ack
  23. Worker downloads model from R2 (signed URL, verifies hash)
  24. Worker downloads input from R2 (signed URL, verifies hash)
  25. Worker recomputes fingerprint, compares with expected
  26. Worker runs inference with fixed checkpoints, builds Merkle tree
  27. Worker signs EIP-712 proof envelope with worker signing key
  28. Worker uploads result to R2 (signed URL)
  29. Worker calls POST /v1/worker/leases/{id}/complete with proof envelope

Backend:
  30. Backend receives proof, runs 12-step verification
  31. Backend calls submitProof on contract (onlyVerifier)
  32. Backend calls verifyJob on contract (isValid=true)
  33. Contract credits provider pendingWithdrawals
  34. Provider calls withdraw() to claim earnings

User:
  35. Dashboard shows completed status (polled every 5-10s)
  36. User downloads result via expiring signed URL
  37. User sees PoAE evidence: fingerprint, Merkle root, output hash, provider, verdict
  38. User sees settlement transaction on Arbitrum Sepolia explorer
```

### 5.4 Flow 3: Job Failure and Refund

```
Failure path (worker crash, invalid proof, timeout):
  - Worker lease expires → job retried once on another node
  - If retry fails or proof is invalid → job status → refunded
  - If no assignment before jobDeadline → user calls requestTimeoutRefund
  - Contract credits user pendingWithdrawals
  - User calls withdraw() to reclaim funds
```

---

## 6. System Architecture

### 6.1 Technology Stack

| Layer | Technology | Responsibility |
|---|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS, Vercel | Wallet login, submission, dashboards |
| Backend API | FastAPI, SQLAlchemy, Alembic, Google Cloud Run deployed demo API host | Public request handling only; no continuous hosted runners |
| Demonstration execution | Owner laptop | The owner laptop runs the worker and five controlled runners only during supervised testing and faculty demonstrations |
| Database | PostgreSQL (Supabase free tier) | Workflow state, leases, proof audit, auth challenges |
| Object Storage | Private Cloudflare R2 | Model artifacts, inputs, results, proof envelopes |
| Cache | Upstash Redis (optional) | Auth challenge caching, rate limiting |
| Blockchain | Arbitrum Sepolia Testnet | Escrow custody and settlement events |
| Contract Tooling | Solidity 0.8.20, Foundry, OpenZeppelin v5 (pinned) | Escrow implementation and tests |
| Worker | Python 3.10+, PyTorch, CUDA | Model inference and PoAE generation |
| IPFS | Pinata (optional stretch) | Optional result publication |

### 6.2 Source-of-Truth Boundaries

- **PostgreSQL** is authoritative for application workflow and lease state.
- **The contract** is authoritative for escrow balance and settlement state.
- **R2** is authoritative for retained model, input, result, and proof objects.
- **The backend** reconciles PostgreSQL against confirmed contract events.

### 6.3 Environments

- Local development uses local PostgreSQL and S3-compatible storage where practical.
- Staging uses the same service types as production and the same Arbitrum Sepolia contract.
- Production is still a testnet MVP environment, not a mainnet environment.
- All URLs come from environment variables; custom domains are optional.

---

## 7. Canonical Identifiers and Encoding

### 7.1 Job ID

The job ID is a UUIDv4 generated by the backend before blockchain submission. It is used everywhere:

| Location | Format |
|---|---|
| PostgreSQL `jobs.id` | Native UUID column |
| REST API responses | Standard 36-character textual UUID |
| Worker requests | Same 36-character textual UUID |
| Smart contract `jobs` mapping key | `bytes32` derived from UUID |

### 7.2 UUID to bytes32 Conversion

```text
Canonical encoding:
  1. Remove hyphens from UUID string → 32 hex characters
  2. Decode hex → 16 raw bytes
  3. Left-align in bytes32 → 16 raw bytes + 16 zero bytes

Example:
  UUID string:  "550e8400-e29b-41d4-a716-446655440000"
  Hyphens removed: "550e8400e29b41d4a716446655440000"
  Raw bytes (16): 0x550e8400e29b41d4a716446655440000
  bytes32:        0x550e8400e29b41d4a71644665544000000000000000000000000000000000000
```

### 7.3 bytes32 to UUID Conversion (Off-Chain Only)

```text
  1. Take first 16 bytes of bytes32 → 32 hex characters
  2. Insert hyphens at positions 8, 12, 16, 20 → standard UUID format

Example:
  bytes32: 0x550e8400e29b41d4a71644665544000000000000000000000000000000000000
  Raw hex:  550e8400e29b41d4a716446655440000
  UUID:     550e8400-e29b-41d4-a716-446655440000
```

### 7.4 Rejection Rules

- `bytes32(0)` is invalid and must revert on `createJob`.
- Duplicate `chain_job_id` values must revert on `createJob`.
- The backend must store both the UUID and the bytes32 `chain_job_id` and verify their mapping whenever processing an event.

### 7.5 Golden Test Vectors

Ten canonical UUID→bytes32 conversions must be shared across contract tests, backend tests, and worker tests. Example:

| # | UUID String | Expected bytes32 (hex) |
|---|---|---|
| 1 | `550e8400-e29b-41d4-a716-446655440000` | `550e8400e29b41d4a71644665544000000000000000000000000000000000000` |
| 2 | `6ba7b810-9dad-11d1-80b4-00c04fd430c8` | `6ba7b8109dad11d180b400c04fd430c800000000000000000000000000000000` |
| 3 | `f47ac10b-58cc-4372-a567-0e02b2c3d479` | `f47ac10b58cc4372a5670e02b2c3d479000000000000000000000000000000000` |
| 4 | `a987fbc9-4bab-3078-cf04-133e876e0193` | `a987fbc94bab3078cf04133e876e019300000000000000000000000000000000` |
| 5 | `7c9e6679-7425-40de-944b-e07fc1f90ae7` | `7c9e6679742540de944be07fc1f90ae700000000000000000000000000000000` |

Vectors 6–10 follow the same pattern with additional edge-case UUIDs (all zeros in one segment, max values, etc.).

---

## 8. Deterministic Fingerprint Protocol

### 8.1 Definition

The backend computes the expected fingerprint before escrow creation. The worker independently recomputes it after downloading the exact artifacts. The backend compares the two values.

```text
domainSeparator = "NEBULA_POAE_V1"

fingerprint = SHA256(
    domainSeparator    ||   // 16 bytes, fixed
    jobId              ||   // 16 bytes (UUID raw bytes, left-aligned in bytes32, first 16 bytes used)
    modelId            ||   // length-prefixed UTF-8 (4 bytes length + N bytes string)
    modelVersion       ||   // length-prefixed UTF-8
    modelHash          ||   // 32 bytes (SHA-256 of the exact model artifact file bytes)
    inputHash          ||   // 32 bytes (SHA-256 of the exact uploaded input file bytes)
    preprocessingVersion || // length-prefixed UTF-8
    configHash            // 32 bytes (SHA-256 of canonical inference config JSON)
)
```

### 8.2 Length-Prefixed UTF-8 Encoding

```text
lengthPrefixed(s) = uint32_big_endian(len(utf8_bytes(s))) || utf8_bytes(s)
```

All strings are encoded as 4-byte big-endian length prefix followed by the UTF-8 byte string. No null terminators. No padding.

### 8.3 Forbidden Inputs

The following must never contribute to a fingerprint:

- `pickle.dumps(model.state_dict())` or any Python pickle serialization.
- `datetime.utcnow()` or any date/time value.
- Python runtime-specific object representation.
- Worker-only provided values without backend recomputation.
- Ambiguous string concatenation without length prefixing.

### 8.4 Fingerprint Lifecycle

1. Backend loads model metadata (hash, version, preprocessing version) from `supported_models`.
2. Backend computes `inputHash` from the stored R2 object after upload confirmation.
3. Backend computes `configHash` from the model's fixed inference configuration.
4. Backend computes `fingerprint` using the canonical formula.
5. Backend stores `fingerprint` in the `jobs` table and passes it to `createJob` on-chain.
6. Worker downloads model and input from R2 signed URLs.
7. Worker independently computes `fingerprint` using the same formula.
8. Worker compares its computed fingerprint with the expected fingerprint from the job assignment.
9. Mismatch → worker rejects the attempt, calls `POST /v1/worker/leases/{id}/fail`.

### 8.5 Canonical Inference Config

Each model has a fixed inference configuration that contributes to `configHash`:

```json
{
    "resnet50": {
        "input_size": [224, 224],
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "num_classes": 1000,
        "preprocessing_version": "resnet50-v1"
    },
    "yolov5": {
        "input_size": [640, 640],
        "confidence_threshold": 0.25,
        "preprocessing_version": "yolov5-v1"
    },
    "bert-base": {
        "max_length": 512,
        "tokenizer": "bert-base-uncased",
        "preprocessing_version": "bert-v1"
    },
    "whisper-tiny": {
        "sample_rate": 16000,
        "max_duration_seconds": 30,
        "preprocessing_version": "whisper-v1"
    }
}
```

`configHash = SHA256(canonical_utf8_json(config))`.

---

## 9. PoAE Proof Envelope and Verification

### 9.1 EIP-712 Typed-Data Proof Envelope

The worker signs an EIP-712 typed-data structure, not a free-form string. This prevents cross-chain, cross-contract, cross-job, cross-lease, and cross-attempt replay.

```solidity
struct ProofEnvelope {
    uint256 protocolVersion;      // e.g., 1
    uint256 chainId;              // e.g., 421614 (Arbitrum Sepolia)
    address verifyingContract;    // NebulaVerifiableAI contract address
    bytes32 jobId;                // chain_job_id (UUID → bytes32)
    bytes32 attemptId;            // job_attempts.id (UUID → bytes32)
    bytes32 leaseId;              // leases.lease_id (UUID → bytes32)
    address provider;             // payout wallet, fixed by assignProvider
    bytes32 fingerprint;          // deterministic fingerprint
    bytes32 merkleRoot;           // Merkle root of execution trace
    bytes32 outputHash;           // SHA-256 of canonical output
    uint256 proofTimestamp;       // Unix timestamp of proof creation
    uint256 leaseExpiresAt;       // Must be > proofTimestamp
}
```

### 9.2 Domain Separator

```solidity
bytes32 DOMAIN_SEPARATOR = keccak256(abi.encode(
    keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
    keccak256("NebulaVerifiableAI"),
    keccak256("1"),
    block.chainid,
    address(this)
));
```

### 9.3 Signing Process (Worker)

```text
1. Construct ProofEnvelope struct with all fields.
2. Compute structHash = keccak256(abi.encode(TYPEHASH, ...fields)).
3. Compute digest = keccak256("\x19\x01" || DOMAIN_SEPARATOR || structHash).
4. Sign digest with worker's secp256k1 signing key (separate from provider wallet).
5. Include (v, r, s) signature and signer address in proof submission.
```

### 9.4 Backend Verification Sequence (12 Steps)

| Step | Check | Failure Outcome |
|---|---|---|
| 1 | Schema and protocol version valid | Reject |
| 2 | Job exists and is in `ProofSubmitted` state | Reject |
| 3 | Attempt exists and belongs to this job | Reject |
| 4 | Lease exists, is active, and not expired | Reject |
| 5 | `proofTimestamp <= leaseExpiresAt` | Reject |
| 6 | Fingerprint matches backend-expected fingerprint (canonical bytes comparison) | Reject, security event |
| 7 | Checkpoint names, order, count, and encoding match model adapter specification | Reject |
| 8 | Merkle root rebuilt from canonical trace leaves + output hash matches submitted `merkleRoot` | Reject |
| 9 | EIP-712 signature recovered address matches the assigned node's authorized worker signer | Reject, node disabled |
| 10 | No replay: this `(jobId, attemptId, leaseId)` combination has not been used before | Reject |
| 11 | Canonical result bytes match `outputHash` | Reject |
| 12 | No prior verdict exists for this job | Reject |

Each check is stored individually in the `proofs` table. One final verdict (`VALID` or `INVALID`) is recorded before settlement is enqueued.

### 9.5 Worker Signature vs Provider Wallet

- **Worker signing key:** A separate secp256k1 key generated during worker setup. The provider authorizes its public address for one node using the provider wallet. The provider wallet private key never enters worker configuration.
- **Provider payout wallet:** Fixed by `assignProvider()` on-chain. Cannot be replaced during proof submission. The EIP-712 envelope includes `provider` (the payout wallet address), and the backend verifies the worker signer is authorized for the node assigned to this provider.

### 9.6 Golden Proof Envelope Test Vectors

Ten golden test vectors must be shared across contract, backend, and worker tests. Each vector specifies:

| Field | Description |
|---|---|
| Input fields | All ProofEnvelope fields |
| Canonical encoding | ABI-encoded struct hash |
| Domain separator | Computed for known chainId and contract address |
| Typed-data digest | Final keccak256 hash |
| Expected signer | Known worker signing key address |
| Expected recovered address | Must match signer |
| Expected Merkle root | For golden checkpoint data |

### 9.7 Required Tamper Cases (10)

Every required tamper case must have a passing test that rejects the tampered proof:

| # | Tamper Case | Expected Result |
|---|---|---|
| 1 | Changed model artifact hash | Fingerprint mismatch → INVALID |
| 2 | Changed input hash | Fingerprint mismatch → INVALID |
| 3 | Missing checkpoint | Checkpoint count/order mismatch → INVALID |
| 4 | Additional checkpoint | Checkpoint count/order mismatch → INVALID |
| 5 | Reordered checkpoint | Checkpoint order mismatch → INVALID |
| 6 | Modified checkpoint hash | Merkle root mismatch → INVALID |
| 7 | Changed output bytes | Output hash mismatch → INVALID |
| 8 | Wrong worker signer or provider | Signature recovery mismatch → INVALID |
| 9 | Expired proof (proofTimestamp > leaseExpiresAt) | Lease freshness check → INVALID |
| 10 | Reused lease/attempt on another job | Replay detection → INVALID |

---

## 10. Job, Attempt, and Lease State Machines

### 10.1 Job State Machine

```solidity
enum JobState {
    None,           // Default: no job exists at this ID
    Created,        // Escrow created on-chain, awaiting blockchain confirmation
    Assigned,       // Provider and lease assigned, worker can execute
    ProofSubmitted, // Worker submitted proof envelope, awaiting verification
    Settled,        // Verifier accepted proof, payment credited (terminal)
    Refunded,       // Refunded to user (terminal)
}
```

### 10.2 Valid Job Transitions

| From State | Trigger | To State | Conditions |
|---|---|---|---|
| None | `createJob` | Created | Valid UUID, non-zero fingerprint, USDC approval for jobPrice |
| Created | `assignProvider` (initial) | Assigned | OnlyVerifier, node eligible, lease created, newProvider != address(0), newLeaseId != bytes32(0), block.timestamp < newLeaseExpiresAt, newLeaseExpiresAt <= job.deadline |
| Assigned | `assignProvider` (reassign) | Assigned | OnlyVerifier, previous lease strictly expired (block.timestamp > oldLeaseExpiresAt), newLeaseId != oldLeaseId, newProvider != address(0), newLeaseId != bytes32(0), block.timestamp < newLeaseExpiresAt, newLeaseExpiresAt <= job.deadline |
| Assigned | `submitProof` | ProofSubmitted | OnlyVerifier, submitted leaseId == job.leaseId, lease not expired (block.timestamp <= job.leaseExpiresAt), job deadline not expired (block.timestamp <= job.deadline) |
| ProofSubmitted | `verifyJob(true)` | Settled | Verifier only, all 12 checks pass |
| ProofSubmitted | `verifyJob(false)` | Refunded | Verifier only, any check fails |
| Created | `requestTimeoutRefund` | Refunded | Only job creator, block.timestamp > jobDeadline |
| Assigned | `requestTimeoutRefund` | Refunded | Only job creator, block.timestamp > jobDeadline |
| ProofSubmitted | `requestTimeoutRefund` | Refunded | Only job creator, block.timestamp > jobDeadline |

**Terminal states:** `Settled`, `Refunded` — no further transitions allowed.

### 10.3 Lease State Machine

```text
None → Active → Expired
Active → Completed (proof accepted)
Active → Failed (proof rejected or error)
Active → Expired (lease timeout, no heartbeat involvement)
```

Heartbeats update worker and lease liveness in PostgreSQL only. A heartbeat must not extend the on-chain `leaseExpiresAt`. The MVP uses fixed one-hour leases. On-chain lease expiry is immutable once set.

A lease may expire and be reassigned (new lease created) while the overall job remains in `Created` or `Assigned` state. The job's `current_attempt` counter increments on each new lease.

### 10.4 Attempt Lifecycle

Each lease creates one `job_attempts` record. An attempt tracks:

- The assigned node
- The lease ID
- Start time, completion time
- Status (running, completed, failed, expired)
- Error message (if failed)
- Proof envelope data (if completed)

After the retry budget is exhausted (`current_attempt >= max_attempts`), the backend sets the database status to `attempts_exhausted`. The on-chain state remains Created (never assigned) or Assigned (was assigned). No new leases may be issued. The database transitions to `awaiting_timeout_refund` once the deadline approaches. The user calls `requestTimeoutRefund()` after `jobDeadline`. The confirmed `TimeoutRefundCredited` event transitions the database to `refunded`.

### 10.5 State Transition Enforcement

All state transitions are enforced by the backend workflow service inside database transactions. The smart contract enforces on-chain state transitions for `createJob`, `submitProof`, `verifyJob`, and `requestTimeoutRefund`. The backend is the authoritative transition controller for the full lifecycle.

### 10.6 Database States vs On-Chain States

The PostgreSQL `jobs.status` column tracks backend workflow state. The on-chain `JobState` enum tracks smart contract state. These are distinct:

| DB status | On-chain state | Meaning |
|---|---|---|
| `pending_blockchain` | `None` | DB record created, awaiting escrow tx |
| `queued` | `Created` | Escrow confirmed, awaiting provider assignment |
| `assigned` | `Assigned` | Provider and lease active on-chain |
| `running` | `Assigned` | Worker executing, lease active |
| `proof_submitted` | `ProofSubmitted` | Proof envelope submitted on-chain |
| `verifying` | `ProofSubmitted` | Backend verifying proof |
| `settling` | `ProofSubmitted` | Verifier calling verifyJob |
| `completed` | `Settled` | Payment credited |
| `retry_pending` | `Assigned` | Lease expired; DB refs cleared, new lease pending chain confirmation |
| `attempts_exhausted` | `Created` or `Assigned` | All attempts exhausted; awaiting jobDeadline |
| `awaiting_timeout_refund` | `Created` or `Assigned` | Deadline near; user eligible for requestTimeoutRefund |
| `refunded` | `Refunded` | Timeout refund confirmed on-chain |
| `expired_pre_escrow` | `None` | Pre-escrow DB record expired; no on-chain state (terminal) |
| `failed` | `Created` or `Assigned` | Unexpected error; may be recoverable |

The backend must never claim an on-chain transition without a confirmed blockchain event. The reconciliation service (Section 13.7) periodically compares DB status against on-chain state and flags discrepancies.

---

## 11. Smart Contract Specification

### 11.1 Contract Interface

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openZeppelin/contracts/token/ERC20/IERC20.sol";
import "@openZeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openZeppelin/contracts/access/Ownable.sol";
import "@openZeppelin/contracts/security/ReentrancyGuard.sol";
import "@openZeppelin/contracts/security/Pausable.sol";

contract NebulaVerifiableAI is Ownable, Pausable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    enum JobState { None, Created, Assigned, ProofSubmitted, Settled, Refunded }

    struct Job {
        address user;
        address provider;           // payout wallet, fixed by assignProvider
        bytes32 chainJobId;         // UUID → bytes32
        bytes32 fingerprint;
        bytes32 merkleRoot;
        bytes32 outputHash;
        bytes32 leaseId;
        uint256 amount;             // USDC base units (6 decimals), always jobPrice at creation
        uint256 createdAt;          // block.timestamp
        uint256 deadline;           // job-level deadline for timeout refund
        uint256 leaseExpiresAt;     // current lease expiry
        uint256 completedAt;        // block.timestamp of settlement
        JobState state;
    }

    IERC20 public immutable usdc;
    address public verifier;
    uint256 public maxJobAmount;
    uint256 public jobPrice;         // contract-configured price per job (base units)
    uint256 public constant JOB_DEADLINE_SECONDS = 24 hours;
    uint256 public constant LEASE_DURATION_SECONDS = 1 hour;

    mapping(bytes32 => Job) public jobs;
    mapping(address => uint256) public pendingWithdrawals;
    uint256 public totalEscrowed;
    uint256 public totalPendingWithdrawals;

    // --- Events ---
    event JobCreated(bytes32 indexed jobId, address indexed user, bytes32 fingerprint, uint256 amount, uint256 deadline);
    // amount is always jobPrice at time of creation
    event ProviderAssigned(bytes32 indexed jobId, address indexed provider, bytes32 leaseId, uint256 leaseExpiresAt);
    event ProofSubmitted(bytes32 indexed jobId, bytes32 indexed leaseId, bytes32 merkleRoot, bytes32 outputHash, address provider);
    event JobSettled(bytes32 indexed jobId, bool valid, uint256 timestamp);
    event PaymentCredited(address indexed recipient, uint256 amount);
    event WithdrawalCompleted(address indexed recipient, uint256 amount);
    event TimeoutRefundCredited(bytes32 indexed jobId, address indexed user, uint256 amount);
    event VerifierUpdated(address indexed oldVerifier, address indexed newVerifier);
    event MaxJobAmountUpdated(uint256 oldMax, uint256 newMax);
    event JobPriceUpdated(uint256 oldPrice, uint256 newPrice);

    // --- Custom Errors ---
    error InvalidUSDC();
    error InvalidVerifier();
    error InvalidAmount();
    error InvalidJobID();
    error InvalidFingerprint();
    error InvalidMerkleRoot();
    error InvalidOutputHash();
    error JobAlreadyExists();
    error JobNotFound();
    error JobNotInState(JobState required, JobState actual);
    error NotJobCreator();
    error NotAssignedProvider();
    error OnlyVerifier();
    error LeaseExpired();
    error LeaseMismatch();
    error JobDeadlineExpired();
    error ProofAlreadySubmitted();
    error NoProofSubmitted();
    error AmountExceedsMax();
    error InvalidJobPrice();
    error RefundTooEarly();
    error RefundAlreadyProcessed();
    error WithdrawInsufficient();
    error TransferFailed();

    constructor(address _usdc) Ownable(msg.sender) {
        if (_usdc == address(0)) revert InvalidUSDC();
        usdc = IERC20(_usdc);
        verifier = msg.sender;
        maxJobAmount = 10e6; // 10 USDC default cap (10_000_000 base units)
        jobPrice = 50_000;   // 0.05 USDC default price (50_000 base units)
    }

    // --- Admin ---
    function setVerifier(address _verifier) external onlyOwner;
    function setMaxJobAmount(uint256 _max) external onlyOwner; // require _max >= jobPrice, emit MaxJobAmountUpdated
    function setJobPrice(uint256 _price) external onlyOwner;   // require _price > 0 && _price <= maxJobAmount, emit JobPriceUpdated
    function pause() external onlyOwner;
    function unpause() external onlyOwner;

    // --- Core ---
    function createJob(bytes32 chainJobId, bytes32 fingerprint) external whenNotPaused returns (bytes32);
    // Transfers exactly jobPrice from msg.sender to contract. All 4 MVP models use this same on-chain price.
    // Per-model on-chain pricing is Post-MVP.

    /// @notice Assign or reassign a provider for a job.
    /// @dev Initial assignment: state must be Created.
    ///      Reassignment: state must be Assigned, previous lease strictly expired,
    ///      new lease ID differs from previous, new provider nonzero,
    ///      newLeaseExpiresAt in future and <= job.deadline.
    ///      Old provider and lease immediately lose authority.
    ///      Emits ProviderAssigned with new provider, lease, and expiry.
    function assignProvider(bytes32 jobId, address provider, bytes32 leaseId, uint64 leaseExpiresAt) external onlyVerifier whenNotPaused;

    /// @notice Submit proof envelope for a job.
    /// @dev Only callable by the verifier (backend). Validates that the submitted
    ///      leaseId matches the job's current lease, the lease has not expired, and
    ///      the job deadline has not passed. Proofs from reassigned or expired leases
    ///      are rejected with LeaseMismatch or LeaseExpired errors.
    function submitProof(bytes32 jobId, bytes32 leaseId, bytes32 merkleRoot, bytes32 outputHash) external onlyVerifier whenNotPaused;

    function verifyJob(bytes32 jobId, bool isValid) external onlyVerifier nonReentrant;
    function requestTimeoutRefund(bytes32 jobId) external nonReentrant;
    function withdraw() external nonReentrant;

    // --- View ---
    function getJob(bytes32 jobId) external view returns (Job memory);
    function getPendingWithdrawal(address account) external view returns (uint256);
}
```

### 11.2 State Transition Rules

| Function | Required State | Result State | Access |
|---|---|---|---|
| `createJob` | `None` | `Created` | Anyone with USDC approval |
| `assignProvider` (initial) | `Created` | `Assigned` | `onlyVerifier` |
| `assignProvider` (reassign) | `Assigned` | `Assigned` | `onlyVerifier`, previous lease expired, new lease ID, new provider nonzero, newExpiry in future and <= deadline |
| `submitProof` | `Assigned` | `ProofSubmitted` | `onlyVerifier`, submitted leaseId == job.leaseId, lease not expired, deadline not expired |
| `verifyJob(true)` | `ProofSubmitted` | `Settled` | `onlyVerifier` |
| `verifyJob(false)` | `ProofSubmitted` | `Refunded` | `onlyVerifier` |
| `requestTimeoutRefund` | `Created`, `Assigned`, or `ProofSubmitted` | `Refunded` | Job creator only, after deadline |
| `withdraw` | N/A (balance-based) | N/A | Any address with pending balance |

### 11.3 submitProof Authorization

`submitProof()` is callable only by the `verifier` address (the backend). The verification and submission ordering is:

1. The contract job is in `Assigned` state (worker has lease).
2. Backend performs 12-step off-chain verification (Section 9.4) while the contract remains in `Assigned`.
3. If the proof is malformed (structurally invalid envelope, bad encoding, unparseable fields), the attempt fails and follows retry/timeout recovery. No contract call is made.
4. If the proof is structurally valid but cryptographically invalid (fingerprint mismatch, Merkle root mismatch, signature mismatch, stale lease), the verdict is `INVALID`. The backend persists the verdict, then calls `submitProof(jobId, leaseId, merkleRoot, outputHash)` on-chain. The contract transitions to `ProofSubmitted`.
5. After confirmed `ProofSubmitted`, the backend calls `verifyJob(jobId, false)` to settle the refund.
6. If the proof is valid, the backend persists the verdict, calls `submitProof(jobId, leaseId, merkleRoot, outputHash)`, waits for confirmed `ProofSubmitted`, then calls `verifyJob(jobId, true)` to settle the payment.

The contract validates:
- State == Assigned
- `leaseId` matches the job's current `leaseId` (rejects stale proofs from reassigned leases)
- `block.timestamp <= job.leaseExpiresAt` (lease not expired)
- `block.timestamp <= job.deadline` (job not expired)

The `provider` address on the job was already fixed by `assignProvider()` and cannot be changed.

**Malformed vs cryptographically invalid proofs:**
- **Malformed:** Envelope cannot be parsed (bad struct encoding, invalid UUID conversion, missing required fields). The attempt fails immediately. The worker's lease expires, triggering retry or timeout recovery. No on-chain state change occurs.
- **Cryptographically invalid:** Envelope parses correctly but fails verification (wrong signature, fingerprint mismatch, Merkle root mismatch, expired proof timestamp). The verdict is `INVALID`. The proof is committed on-chain via `submitProof()`, then settled false via `verifyJob(false)`. The user receives a refund. This distinction matters because structurally valid invalid proofs must be committed to prevent the worker from retrying the same invalid proof indefinitely.

### 11.4 Pause Behavior

| Function | Paused? | Rationale |
|---|---|---|
| `createJob` | Yes | Prevent new jobs during emergency |
| `assignProvider` | Yes | Prevent new assignments during emergency |
| `submitProof` | Yes | Prevent new proofs during emergency |
| `verifyJob` | **No** | Already-submitted proofs must be settled to avoid fund trapping |
| `requestTimeoutRefund` | **No** | Users must always be able to reclaim funds after deadline |
| `withdraw` | **No** | Users and providers must always be able to withdraw credited funds |

### 11.5 Contract Invariants

1. **Conservation:** `usdc.balanceOf(this) >= totalEscrowed + totalPendingWithdrawals` (uses `>=` because unsolicited token transfers may increase balance).
2. **No double settle:** Each job reaches exactly one terminal state.
3. **Lease exclusivity:** At most one lease active or pending_chain per job. Reassignment atomically invalidates previous lease.
4. **Reassignment guards:** Only from Assigned state, only after previous lease strictly expired, only with different lease ID, only before jobDeadline.
5. **Proof lease binding:** submitProof reverts if submitted leaseId differs from current job lease, or if lease/deadline expired.
6. **No double withdraw:** `pendingWithdrawals[account]` is set to zero before transfer in `withdraw()`.
7. **No unauthorized settlement:** Only the verifier can settle. Only the assigned provider receives provider payment.
8. **Timeout safety:** A timed-out job cannot later pay a provider.
9. **Reentrancy safety:** `nonReentrant` on `verifyJob`, `requestTimeoutRefund`, and `withdraw`. CEI pattern enforced.

---

## 12. Payment, Withdrawal, and Refund Accounting

### 12.1 Base Units

All on-chain and database monetary values use integer base units with 6 decimals (USDC standard).

```text
0.01 USDC  =     10,000 base units
0.03 USDC  =     30,000 base units
0.05 USDC  =     50,000 base units  ← default jobPrice
0.10 USDC  =    100,000 base units
1.00 USDC  = 1,000,000 base units
```

The contract-configured `jobPrice` defaults to 50,000 base units (0.05 USDC). `createJob()` transfers exactly `jobPrice` from the user. All four MVP models use this same on-chain price. Per-model on-chain pricing is Post-MVP. The owner can adjust `jobPrice` via `setJobPrice()`, which requires `0 < jobPrice <= maxJobAmount`. `setMaxJobAmount()` requires the new cap to be at least `jobPrice`.

Database columns for on-chain amounts use `NUMERIC(78,0)` — no floating-point or two-decimal `DECIMAL` types.

### 12.2 Pull-Payment Settlement

```text
verifyJob(jobId, true):
  1. Validate state == ProofSubmitted
  2. Set state = Settled, completedAt = block.timestamp
  3. totalEscrowed -= job.amount
  4. pendingWithdrawals[job.provider] += job.amount
  5. totalPendingWithdrawals += job.amount
  6. Emit JobSettled(jobId, true, block.timestamp)
  7. Emit PaymentCredited(job.provider, job.amount)
  8. NO external token transfer

verifyJob(jobId, false):
  1. Validate state == ProofSubmitted
  2. Set state = Refunded, completedAt = block.timestamp
  3. totalEscrowed -= job.amount
  4. pendingWithdrawals[job.user] += job.amount
  5. totalPendingWithdrawals += job.amount
  6. Emit JobSettled(jobId, false, block.timestamp)
  7. Emit TimeoutRefundCredited(jobId, job.user, job.amount)
  8. NO external token transfer
```

### 12.3 Withdrawal

```solidity
function withdraw() external nonReentrant {
    uint256 amount = pendingWithdrawals[msg.sender];
    if (amount == 0) revert WithdrawInsufficient();

    pendingWithdrawals[msg.sender] = 0;
    totalPendingWithdrawals -= amount;

    usdc.safeTransfer(msg.sender, amount);
    emit WithdrawalCompleted(msg.sender, amount);
}
```

CEI pattern: balance zeroed before transfer. If transfer fails, state is reverted atomically.

### 12.4 Timeout Refund

```text
requestTimeoutRefund(jobId):
  1. Validate caller is job.user
  2. Validate job.state is Created, Assigned, or ProofSubmitted (non-terminal)
  3. Validate block.timestamp > job.deadline
  4. Set state = Refunded, completedAt = block.timestamp
  5. totalEscrowed -= job.amount
  6. pendingWithdrawals[job.user] += job.amount
  7. totalPendingWithdrawals += job.amount
  8. Emit TimeoutRefundCredited(jobId, job.user, job.amount)
```

### 12.5 Accounting Safety Property

```text
USDC balance of contract >= totalEscrowed + totalPendingWithdrawals
```

This uses `>=` (not strict equality) because unsolicited token transfers to the contract increase the balance without going through escrow accounting. The invariant must hold at all times after any state-changing function.

---

## 13. Backend Services

### 13.1 Service Responsibilities

| Service | File | Responsibility |
|---|---|---|
| **auth** | `app/services/auth.py` | Challenge generation, JWT create/validate/refresh, wallet signature verification, session management, refresh rotation, reuse detection |
| **jobs** | `app/services/jobs.py` | UUID creation, input upload slot, expected fingerprint computation, blockchain confirmation, idempotency keys, ownership checks, state-transition validation |
| **scheduler** | `app/services/scheduler.py` | Eligible-node filtering, least-loaded selection, row-locked lease acquisition, heartbeat tracking, retry budget, exhaustion → refund |
| **proof_verifier** | `app/services/proof_verifier.py` | 12-step verification sequence (Section 9.4), idempotent verdict recording |
| **blockchain** | `app/services/blockchain.py` | Transaction submission, event listener, confirmation handling, reorg handling, last-finalized-block checkpoint |
| **storage** | `app/services/storage.py` | R2 presigned URL generation (upload + download, 5–15 min, read-only, single-object scoped), IPFS pinning via Pinata (optional) |
| **reconciliation** | `app/services/reconciliation.py` | Contract vs DB state comparison, dropped-transaction recovery, periodic audit |

### 13.2 Authentication Middleware

```text
JWTMiddleware:
  - Extract Bearer token from Authorization header
  - Validate signature, expiry, session revocation
  - Inject user_id and role into request context
  - Worker endpoints use API key authentication (separate from user JWT)
```

### 13.3 Scheduler Details

The scheduler runs as a background task within the FastAPI process:

```text
Every 5 seconds:
  1. Query jobs WHERE state = 'Created' AND no active or pending_chain lease, ORDER BY created_at ASC
  2. For each eligible job:
     a. Acquire row lock on the job (SELECT ... FOR UPDATE)
     b. Filter nodes: status='online', vram >= model requirement, heartbeat < 90s
     c. Select least loaded node (fewest active leases)
     d. If eligible node found:
        - Create lease record with status = 'pending_chain', persist tx_hash and nonce
        - Call assignProvider on contract
        - On confirmed ProviderAssigned event: set lease.status = 'active', update job → Assigned
        - On failed tx: log error, leave lease as 'pending_chain', retry next cycle
     e. If no eligible node: leave in Created, retry next cycle
  3. Check for expired leases:
     - WHERE lease.expires_at < now AND lease.status = 'active'
     - Mark lease as expired
     - Increment job.current_attempt
     - If current_attempt < max_attempts:
       - Set db_status → 'retry_pending'
       - Clear DB assignment references: assigned_node_id = NULL, current_lease_id = NULL
       - Preserve expired lease record (do not delete)
       - Create new lease record with status = 'pending_chain' and new job_attempts record
       - Call reassignment path of assignProvider() on contract
       - On confirmed ProviderAssigned event: set lease.status = 'active', db_status → 'assigned'
       - On failed tx: log error, leave db_status → 'retry_pending', retry next cycle
     - If current_attempt >= max_attempts:
       - Set db_status → 'attempts_exhausted'
       - Do NOT call any contract function
       - On-chain state remains Created or Assigned
       - No new leases may be issued
       - User becomes eligible for requestTimeoutRefund() after jobDeadline
  4. Idempotent blockchain reconciliation:
     - For leases with status = 'pending_chain' and tx_hash set:
       - Query transaction receipt from chain
       - If receipt exists and confirms ProviderAssigned with matching leaseId:
         - Activate lease in DB, update job status to 'assigned'
       - If receipt exists but confirms different leaseId or reverts:
         - Log discrepancy, mark lease as 'failed', clear job assignment
       - If receipt does not exist (tx dropped):
         - Resubmit with same nonce (controlled nonce handling)
       - Never create another lease while previous transaction outcome is uncertain
```

Row locking (`SELECT ... FOR UPDATE`) ensures two scheduler instances cannot assign the same job to two different nodes.

### 13.4 Storage Service

- **Presigned URLs:** Generated by the backend using R2 S3-compatible API. URLs are read-only, scoped to one exact object key, expire in 5–15 minutes, and must never appear in logs.
- **Object keys:** Stored in PostgreSQL, not the signed URLs themselves.
- **Retention:** Inputs expire after 24 hours. Results and proof envelopes expire after 7 days. Models are permanent.
- **IPFS (optional):** Pinata API called by the backend after result upload. IPFS hash stored in DB and optionally displayed.

---

## 14. Worker Architecture

### 14.1 Worker Components

```text
worker/
├── worker.py              # Main entry point, async event loop
├── config.py              # Pydantic settings from .env
├── core/
│   ├── executor.py        # Job execution orchestrator
│   ├── model_loader.py    # Download from R2, hash verify, cache
│   ├── preprocessor.py    # Model-specific input preprocessing
│   └── tracer.py          # Fixed checkpoint execution trace
├── proof/
│   ├── fingerprint.py     # Deterministic fingerprint computation
│   ├── merkle.py          # Merkle tree construction
│   └── signer.py          # EIP-712 typed-data signing
└── storage/
    ├── r2_upload.py       # Result upload via presigned URL
    └── ipfs_pin.py        # IPFS pin via backend (optional)
```

### 14.2 Worker Signing Key

- Worker setup generates a fresh secp256k1 key pair.
- The public key (Ethereum address) is registered with the backend and authorized for one node.
- The provider wallet private key **never** enters worker configuration.
- The worker signs all proof envelopes with its dedicated signing key.

### 14.3 Deterministic Fingerprint (Worker Side)

The worker recomputes the fingerprint using the same canonical formula as the backend:

```python
def compute_fingerprint(model_hash: bytes, input_hash: bytes, job: dict) -> bytes:
    domain = b"NEBULA_POAE_V1"
    job_id_bytes = uuid_to_bytes32(job["job_id"])[:16]
    model_id = length_prefixed(job["model_id"])
    model_version = length_prefixed(job["model_version"])
    preprocessing_version = length_prefixed(job["preprocessing_version"])
    config_hash = sha256(canonical_config_json(job["model_id"]))

    return sha256(
        domain
        + job_id_bytes
        + model_id
        + model_version
        + model_hash
        + input_hash
        + preprocessing_version
        + config_hash
    )
```

### 14.4 Fixed Checkpoints (Not Dynamic)

Each model adapter defines fixed named checkpoints in code, not discovered via `model.children()` at runtime.

**ResNet50 adapter example:**

```text
Checkpoint 0: "layer1_layer1.0_conv1"    — after layer1.0.conv1 + BN + ReLU
Checkpoint 1: "layer2_layer2.0_conv1"    — after layer2.0.conv1 + BN + ReLU
Checkpoint 2: "layer3_layer3.0_conv1"    — after layer3.0.conv1 + BN + ReLU
Checkpoint 3: "layer4_layer4.0_conv1"    — after layer4.0.conv1 + BN + ReLU
```

Each checkpoint hash binds:
- Protocol version
- Checkpoint index and name
- Tensor data type and shape
- Canonical contiguous tensor bytes

### 14.5 Merkle Tree Construction (Canonical Algorithm)

The Merkle tree algorithm is defined explicitly. Backend and worker must use the identical implementation. Do not rely on library defaults or undocumented behavior.

```text
Algorithm: Canonical Merkle Tree Construction

Input: ordered list of leaf data items [leaf_0, leaf_1, ..., leaf_n]
       where leaf_i = checkpoint_i_hash for i < n, and leaf_n = output_hash
       Leaf order is fixed by the model adapter; never sort leaves.

Step 1 — Compute leaf hashes (preserve order):
    For each leaf_i in order:
        leafHash_i = SHA256(0x00 || canonicalLeafBytes(leaf_i))
    where canonicalLeafBytes(h) = bytes.fromhex(h)  // 32 bytes from hex string

Step 2 — Build tree bottom-up:
    level = [leafHash_0, leafHash_1, ..., leafHash_n]
    While len(level) > 1:
        If len(level) is odd:
            Duplicate the final node: level.append(level[-1])
        nextLevel = []
        For i in range(0, len(level), 2):
            left = level[i]
            right = level[i+1]
            parent = SHA256(0x01 || left || right)
            nextLevel.append(parent)
        level = nextLevel

Step 3 — Root:
    root = level[0]  // 32 bytes, represented as hex string (64 hex chars)
```

**Prefix convention:**
- Leaf prefix: `0x00` (1 byte)
- Internal node prefix: `0x01` (1 byte)
- This prevents second-preimage attacks where an internal node could be mistaken for a leaf.

**Odd-node handling:**
- When a level has an odd number of nodes, the final node is duplicated and hashed with itself.
- Example: 3 leaves → [H0, H1, H2] → duplicate H2 → [H0, H1, H2, H2] → parents: [SHA256(0x01||H0||H1), SHA256(0x01||H2||H2)] → root: SHA256(0x01||parent0||parent1)

**Golden vectors must include:**
- Input leaf data items (hex)
- Computed leaf hashes (hex, with 0x00 prefix applied)
- Every intermediate tree level (hex)
- Final root (hex)

**Dependency:** The worker and backend must implement this algorithm directly. Do not use `MerkleTools`, `merkletools`, or any library that does not follow this exact prefix-and-duplicate convention. If a library is used, it must be verified to produce identical output for all golden test vectors.

### 14.6 Worker Lifecycle Requests

Every lifecycle request from the worker must include:

- `job_id` (UUID)
- `attempt_id` (UUID)
- `lease_id` (UUID)
- `node_id` (UUID)

The backend validates that these all reference the same active lease.

### 14.7 Worker Corrections (Documented, Not Implemented)

The following corrections to the existing worker scaffold are required before implementation:

1. Add `import asyncio` to `executor.py`.
2. Replace pickle+datetime fingerprint with deterministic formula.
3. Replace dynamic `model.children()` tracing with fixed named checkpoints.
4. Cache BERT tokenizer during `__init__` (not re-downloaded per inference).
5. Use proper mel-spectrogram pipeline for Whisper (not raw float32 truncation).
6. Fix fallback preprocessor: `torch.tensor(list(input_data))` not `torch.tensor(bytes)`.
7. Implement `_get_next_job()` → `POST /v1/worker/leases/next`.
8. Implement `_notify_completion()` → `POST /v1/worker/leases/{id}/complete`.
9. Implement `_notify_failure()` → `POST /v1/worker/leases/{id}/fail`.
10. Implement 30-second heartbeat → `POST /v1/worker/heartbeat`.
11. Verify model and input hashes before execution.
12. Sign canonical EIP-712 proof envelope with worker signing key.
13. Stop execution if lease expires before inference begins.
14. Never log API keys, signed URLs, tokens, or raw private inputs.

---

## 15. Database Schema

### 15.1 Twelve Canonical Tables

| # | Table | Purpose |
|---|---|---|
| 1 | `users` | Wallet-identified participants |
| 2 | `supported_models` | Approved model registry |
| 3 | `nodes` | GPU node registrations |
| 4 | `jobs` | Inference jobs, state, hashes, timestamps |
| 5 | `payments` | Payment ledger (on-chain confirmed) |
| 6 | `auth_challenges` | Single-use wallet login nonces |
| 7 | `auth_sessions` | Hashed revocable session tokens |
| 8 | `leases` | Time-bounded exclusive job assignments |
| 9 | `job_attempts` | Per-attempt execution records |
| 10 | `proofs` | Proof envelopes and verification results |
| 11 | `chain_transactions` | On-chain transaction log |
| 12 | `blockchain_events` | Raw blockchain event ingestion |

### 15.2 Table Definitions

#### `users`

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wallet_address VARCHAR(42) UNIQUE NOT NULL,
    role VARCHAR(20) CHECK (role IN ('user', 'provider')),
    created_at TIMESTAMPTZ DEFAULT now()
);
```

#### `supported_models`

```sql
CREATE TABLE supported_models (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    framework VARCHAR(50),
    model_source_url VARCHAR(500),
    model_hash_sha256 VARCHAR(64),
    model_version VARCHAR(50),
    preprocessing_version VARCHAR(50),
    vram_required_gb INT,
    estimated_inference_ms INT,
    max_input_size_mb INT,
    supported_formats JSONB,
    price_base_units NUMERIC(78,0) NOT NULL,
    input_type VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT now()
);
```

Seed data: 4 models with real artifact hashes (not placeholders) and base-unit prices.

#### `nodes`

```sql
CREATE TABLE nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id UUID NOT NULL REFERENCES users(id),
    gpu_name VARCHAR(100),
    vram_gb INT,
    cuda_capable BOOLEAN DEFAULT true,
    location VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'online', 'offline', 'disabled')),
    worker_signer_address VARCHAR(42),
    api_key_hash VARCHAR(64) NOT NULL,
    active_leases INT DEFAULT 0,
    last_heartbeat TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_nodes_status ON nodes(status);
CREATE INDEX idx_nodes_provider ON nodes(provider_id);
```

#### `jobs`

```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    model_id VARCHAR(50) NOT NULL REFERENCES supported_models(id),
    chain_job_id VARCHAR(66) UNIQUE NOT NULL,
    assigned_node_id UUID REFERENCES nodes(id),
    current_lease_id UUID,
    status VARCHAR(50) DEFAULT 'pending_blockchain'
        CHECK (status IN (
            'pending_blockchain', 'queued', 'assigned', 'running',
            'proof_submitted', 'verifying', 'settling', 'completed',
            'retry_pending', 'attempts_exhausted', 'awaiting_timeout_refund',
            'refunded', 'expired_pre_escrow', 'failed'
        )),
    input_file_key VARCHAR(500),
    input_hash VARCHAR(64),
    result_file_key VARCHAR(500),
    result_ipfs_hash VARCHAR(100),
    expected_fingerprint VARCHAR(64),
    price_base_units NUMERIC(78,0) NOT NULL,
    error_message TEXT,
    blockchain_tx_hash VARCHAR(255),
    blockchain_escrow_amount NUMERIC(78,0),
    deadline TIMESTAMPTZ NOT NULL,
    max_attempts INT DEFAULT 3 CHECK (max_attempts > 0),
    current_attempt INT DEFAULT 0 CHECK (current_attempt >= 0),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_jobs_user ON jobs(user_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created ON jobs(created_at DESC);
```

#### `payments`

```sql
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    user_id UUID NOT NULL REFERENCES users(id),
    provider_id UUID REFERENCES users(id),
    amount_base_units NUMERIC(78,0) NOT NULL,
    payment_type VARCHAR(20) CHECK (payment_type IN ('provider_credit', 'user_refund')),
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'credited', 'withdrawn')),
    blockchain_tx_hash VARCHAR(255) UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    credited_at TIMESTAMPTZ,
    withdrawn_at TIMESTAMPTZ
);
```

#### `auth_challenges`

```sql
CREATE TABLE auth_challenges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wallet_address VARCHAR(42) NOT NULL,
    nonce VARCHAR(64) UNIQUE NOT NULL,
    message TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_auth_challenges_wallet ON auth_challenges(wallet_address);
```

#### `auth_sessions`

```sql
CREATE TABLE auth_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    token_hash VARCHAR(64) UNIQUE NOT NULL,
    refresh_token_hash VARCHAR(64) UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    replaced_by_session_id UUID,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id);
```

Never store plaintext tokens. Access tokens: 24-hour expiry. Refresh tokens: 7-day expiry, httpOnly secure cookie.

#### `leases`

```sql
CREATE TABLE leases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    node_id UUID NOT NULL REFERENCES nodes(id),
    lease_id VARCHAR(66) UNIQUE NOT NULL,
    started_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    heartbeat_at TIMESTAMPTZ,
    status VARCHAR(50) DEFAULT 'pending_chain' CHECK (status IN ('pending_chain', 'active', 'expired', 'completed', 'failed')),
    tx_hash VARCHAR(66),
    nonce BIGINT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX idx_one_active_lease_per_job ON leases(job_id) WHERE status IN ('active', 'pending_chain');
```

At most one active or pending_chain lease per job is enforced by the partial unique index. The `tx_hash` and `nonce` columns support idempotent blockchain reconciliation.

#### `job_attempts`

```sql
CREATE TABLE job_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    node_id UUID NOT NULL REFERENCES nodes(id),
    lease_id UUID NOT NULL REFERENCES leases(id),
    attempt_number INT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(50) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'expired')),
    error TEXT,
    fingerprint_hash VARCHAR(64),
    merkle_root VARCHAR(66),
    output_hash VARCHAR(64),
    signature TEXT,
    UNIQUE (job_id, attempt_number)
);
```

#### `proofs`

```sql
CREATE TABLE proofs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_attempt_id UUID NOT NULL REFERENCES job_attempts(id),
    protocol_version INT NOT NULL DEFAULT 1,
    fingerprint_hash VARCHAR(64) NOT NULL,
    merkle_root VARCHAR(66) NOT NULL,
    output_hash VARCHAR(64) NOT NULL,
    signature TEXT NOT NULL,
    signer_address VARCHAR(42) NOT NULL,
    trace_hashes JSONB,
    proof_timestamp TIMESTAMPTZ NOT NULL,
    valid BOOLEAN,
    verification_error TEXT,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

#### `chain_transactions`

```sql
CREATE TABLE chain_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chain_id INT NOT NULL,
    contract_address VARCHAR(42) NOT NULL,
    job_id UUID REFERENCES jobs(id),
    tx_hash VARCHAR(66) UNIQUE NOT NULL,
    tx_type VARCHAR(50) NOT NULL CHECK (tx_type IN (
        'createJob', 'assignProvider', 'submitProof',
        'verifyJob', 'requestTimeoutRefund', 'withdraw'
    )),
    from_address VARCHAR(42) NOT NULL,
    to_address VARCHAR(42) NOT NULL,
    amount_base_units NUMERIC(78,0),
    block_number BIGINT,
    block_hash VARCHAR(66),
    status VARCHAR(50) DEFAULT 'submitted' CHECK (status IN ('submitted', 'confirmed', 'finalized', 'dropped')),
    created_at TIMESTAMPTZ DEFAULT now()
);
```

#### `blockchain_events`

```sql
CREATE TABLE blockchain_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chain_id INT NOT NULL,
    contract_address VARCHAR(42) NOT NULL,
    transaction_hash VARCHAR(66) NOT NULL,
    log_index INT NOT NULL,
    block_number BIGINT NOT NULL,
    block_hash VARCHAR(66) NOT NULL,
    event_name VARCHAR(100) NOT NULL,
    job_id UUID REFERENCES jobs(id),
    event_data JSONB,
    confirmation_status VARCHAR(50) DEFAULT 'pending' CHECK (confirmation_status IN ('pending', 'confirmed', 'finalized')),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (chain_id, contract_address, transaction_hash, log_index)
);

CREATE INDEX idx_blockchain_events_job ON blockchain_events(job_id);
```

---

## 16. API Contract

### 16.1 Canonical Endpoint Table

| Method | Endpoint | Auth | Idempotent | Description |
|---|---|---|---|---|
| `POST` | `/v1/auth/challenge` | None | No | Create wallet-signature challenge |
| `POST` | `/v1/auth/verify` | None | No | Verify signature, start session (24h access + 7d refresh) |
| `POST` | `/v1/auth/refresh` | Refresh cookie | Yes | Refresh expired access token |
| `POST` | `/v1/auth/logout` | JWT | Yes | Revoke session |
| `GET` | `/v1/models` | None | Yes | List enabled models with pricing |
| `GET` | `/v1/models/{model_id}` | None | Yes | Model details and input policy |
| `POST` | `/v1/jobs/upload` | JWT | Yes | Create presigned R2 upload slot for input |
| `POST` | `/v1/jobs` | JWT | Yes | Create pre-escrow job (validates upload, computes fingerprint) |
| `POST` | `/v1/jobs/{id}/confirm-escrow` | JWT | Yes | Confirm blockchain escrow event |
| `GET` | `/v1/jobs` | JWT | Yes | List user's jobs |
| `GET` | `/v1/jobs/{id}` | JWT + ownership | Yes | Job details, PoAE status, settlement |
| `GET` | `/v1/jobs/{id}/result-url` | JWT + ownership | Yes | Authorized result download URL (5min) |
| `POST` | `/v1/nodes` | JWT | Yes | Register provider node |
| `POST` | `/v1/nodes/{id}/credentials/rotate` | JWT + ownership | Yes | Rotate node API credential |
| `GET` | `/v1/providers/me` | JWT | Yes | Provider nodes and earnings |
| `POST` | `/v1/worker/heartbeat` | API key | Yes | Update node health (30s interval) |
| `POST` | `/v1/worker/leases/next` | API key | Yes | Acquire next compatible lease |
| `POST` | `/v1/worker/leases/{id}/ack` | API key | Yes | Acknowledge lease before download |
| `POST` | `/v1/worker/leases/{id}/result-upload` | API key | Yes | Create presigned R2 upload slot for result |
| `POST` | `/v1/worker/leases/{id}/complete` | API key | Yes | Submit EIP-712 proof envelope |
| `POST` | `/v1/worker/leases/{id}/fail` | API key | Yes | Report attempt failure |
| `POST` | `/v1/internal/jobs/{id}/verify` | Internal | Yes | Backend: run 12-step verification and settle |
| `GET` | `/v1/health/live` | None | Yes | Process liveness check |
| `GET` | `/v1/health/ready` | None | Yes | Dependency readiness check |

### 16.2 Authentication Per Endpoint

| Auth Type | Used By |
|---|---|
| None | `/v1/models`, `/v1/health/*`, `/v1/auth/challenge` |
| JWT (Bearer, 24h access) | User endpoints: `/v1/jobs/*`, `/v1/nodes`, `/v1/providers/me` |
| Refresh cookie | `/v1/auth/refresh` |
| API key (Bearer) | Worker endpoints: `/v1/worker/*` |
| Internal (IP allowlist or shared secret) | `/v1/internal/*` |

### 16.3 Idempotency

All mutating retryable endpoints require an `Idempotency-Key` header (UUID). The backend stores the key and response for 24 hours and returns the cached response for duplicate requests.

### 16.4 Error Responses

```json
{
    "error": "string",
    "message": "human-readable description",
    "details": {}
}
```

Standard HTTP status codes: 400 (validation), 401 (unauthenticated), 403 (unauthorized), 404 (not found), 409 (conflict/duplicate), 413 (payload too large), 429 (rate limited), 500 (internal).

---

## 17. Storage Architecture

### 17.1 Object Categories

| Category | Storage | Access | Retention |
|---|---|---|---|
| Model artifacts | Private R2 | Signed URL (worker download, 5min) | Permanent |
| Input files | Private R2 | Signed URL (user upload 5min, worker download 5min) | 24 hours |
| Result files | Private R2 | Signed URL (user download 5min, IPFS optional) | 7 days |
| Proof envelopes | Private R2 | Signed URL (user/auditor download 5min) | 7 days |

### 17.2 Signed URL Rules

- Read-only.
- Scoped to one exact object key.
- Expire in 5–15 minutes.
- Issued only for active leases or authenticated ownership.
- Redacted from all logs.
- The backend stores object keys in PostgreSQL, not the signed URLs.

### 17.3 Model Download Flow

1. Worker calls `POST /v1/worker/leases/next`, receives job with model metadata.
2. Worker calls `GET /v1/models/{model_id}` to get the presigned R2 download URL.
3. Worker downloads model bytes directly from R2 (no backend proxy).
4. Worker computes SHA-256 of downloaded bytes.
5. Worker compares with `model_hash_sha256` from registry.
6. Mismatch → reject attempt, report failure.

### 17.4 IPFS (Optional Stretch)

- After result upload to R2, backend optionally calls Pinata API to pin the result.
- IPFS hash stored in `jobs.result_ipfs_hash`.
- IPFS publication is opt-in, not required for MVP launch.

---

## 18. Authentication and Authorization

### 18.1 Wallet-Signature Challenge

```text
POST /v1/auth/challenge
Request: { "wallet_address": "0x..." }
Response: {
    "challenge": "Sign this message to authenticate with Nebula AI Cloud.\n\nWallet: 0x...\nNonce: <random 32-byte hex>\nIssued: <ISO8601>\nExpires: <ISO8601 + 5 minutes>",
    "expires_at": "<ISO8601>"
}
```

The challenge includes:
- Domain binding (application name)
- Wallet address
- Chain ID
- Nonce (random, single-use, 5-minute expiry)
- Issued-at and expiration timestamps

### 18.2 JWT Session

```text
POST /v1/auth/verify
Request: { "wallet_address": "0x...", "signature": "0x...", "challenge_id": "..." }
Response: Set-Cookie: refresh_token=<token>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth/refresh; Max-Age=604800
          { "access_token": "<JWT>", "expires_in": 86400 }
```

Access token payload:
```json
{
    "sub": "<user_id>",
    "wallet": "0x...",
    "role": "user|provider",
    "iat": 1234567890,
    "exp": 1234654290
}
```

### 18.3 Refresh Rotation

- Refresh tokens are stored as SHA-256 hashes in `auth_sessions`.
- On refresh, the old session is marked `replaced_by_session_id` and a new session is created.
- Reuse detection: if a revoked refresh token is presented, all sessions for that user are revoked.

### 18.4 Worker Credentials

Workers use API key authentication, separate from user JWT sessions:

- API key generated on node registration, displayed once, stored as SHA-256 hash.
- Credential can be rotated (`POST /v1/nodes/{id}/credentials/rotate`).
- Credential can be revoked (node status → `disabled`).
- Worker endpoints validate API key, not JWT.

### 18.5 Rate Limiting

| Endpoint Category | Limit |
|---|---|
| Auth endpoints | 10 per minute per IP |
| Job creation | 5 per minute per user |
| Worker heartbeat | 1 per 30 seconds per node |
| Global | 100 per 15 minutes per IP |

---

## 19. Blockchain Event Processing and Reconciliation

### 19.1 Event Listener

The backend runs an event listener that:

1. Connects to Arbitrum Sepolia via WebSocket (or HTTP polling fallback).
2. Subscribes to contract events: `JobCreated`, `ProviderAssigned`, `ProofSubmitted`, `JobSettled`, `PaymentCredited`, `TimeoutRefundCredited`, `WithdrawalCompleted`.
3. Ingests events idempotently (checks `blockchain_events` uniqueness constraint).
4. Updates PostgreSQL job state and payment records based on confirmed events.
5. Tracks confirmation depth (pending → confirmed at 1 block → finalized at 10+ blocks).

### 19.2 Idempotent Event Ingestion

```text
For each event:
  1. Check (chain_id, contract_address, transaction_hash, log_index) uniqueness
  2. If already exists: skip
  3. If new: insert into blockchain_events, update job/payment state
  4. If event contradicts DB state: log discrepancy, flag for reconciliation
```

### 19.3 Chain Reorganization Handling

- Events are marked `confirmed` after 1 block.
- Events are marked `finalized` after 10+ blocks.
- On reorg, un-finalized events are re-processed.
- The `blockchain_events` table tracks block hashes for reorg detection.

### 19.4 Reconciliation

A periodic reconciliation job (every 5 minutes) compares:

1. On-chain `jobs` mapping against PostgreSQL `jobs` table.
2. On-chain `pendingWithdrawals` against PostgreSQL `payments` table.
3. Contract USDC balance against `totalEscrowed + totalPendingWithdrawals`.

Discrepancies are logged and flagged for manual review. Dropped transactions are re-submitted idempotently.

### 19.5 Separation of Transaction States

| State | Meaning |
|---|---|
| `submitted` | Transaction sent to RPC, awaiting confirmation |
| `confirmed` | Transaction included in a block (1+ confirmations) |
| `finalized` | Transaction deeply confirmed (10+ blocks, reorg-safe) |
| `dropped` | Transaction replaced or failed, requires reconciliation |

The database must not treat a user-submitted transaction hash as proof of successful escrow creation. Only confirmed on-chain events are authoritative.

---

## 20. Dashboard Requirements

### 20.1 Update Mechanism

Polling every 5–10 seconds. No WebSocket dependency. WebSocket is Post-MVP only.

### 20.2 User Dashboard

| Element | Data Source |
|---|---|
| Job list with status | `GET /v1/jobs` |
| Job detail + PoAE status | `GET /v1/jobs/{id}` |
| Result download | `GET /v1/jobs/{id}/result-url` |
| PoAE evidence (fingerprint, Merkle root, output hash, provider, verdict) | `GET /v1/jobs/{id}` |
| Settlement/refund transaction | Blockchain explorer link |
| Model pricing and input limits | `GET /v1/models` |

### 20.3 Provider Dashboard

| Element | Data Source |
|---|---|
| Node list with status | `GET /v1/providers/me` |
| Active leases and current job | `GET /v1/providers/me` |
| Earnings (credited and withdrawn) | `GET /v1/providers/me` |
| Node registration | `POST /v1/nodes` |
| Worker download and setup instructions | Static page |
| Credential rotation | `POST /v1/nodes/{id}/credentials/rotate` |

### 20.4 Loading and Error States

All pages must display:
- Loading spinner during API calls.
- Error messages with retry option.
- Transaction pending/confirmed/failed states.
- Empty states with call-to-action.

---

## 21. Testing and Security Invariants

### 21.1 Contract Tests (Foundry)

| Category | Tests |
|---|---|
| **State machine** | Every valid transition, every invalid transition, duplicate creation, duplicate proof, duplicate settlement, settlement after refund, refund after settlement |
| **submitProof lease validation** | Valid proof with correct leaseId succeeds, stale leaseId reverts (LeaseMismatch), expired lease reverts (LeaseExpired), proof after jobDeadline reverts (JobDeadlineExpired), proof from reassigned lease reverts |
| **Lease reassignment** | Initial assignment from Created, reassignment after lease expiry (state stays Assigned), reassignment before expiry reverts, reassignment after jobDeadline reverts (JobDeadlineExpired), reassignment with same lease ID reverts, reassignment from ProofSubmitted reverts, reassignment from terminal state reverts |
| **Attempt exhaustion** | Exhaustion does not call contract, exhaustion prevents new backend leases, timeout refund succeeds after exhausted attempts, timeout refund reverts before deadline |
| **Pull payments** | Provider withdrawal, user refund withdrawal, zero-balance withdrawal, multiple credited jobs, failed token transfer, reentrancy attempt, accounting totals |
| **Timeout** | Refund strictly after deadline, revert before deadline, exact deadline boundary, refund after verifier outage, settlement/timeout race, duplicate timeout request |
| **Pause** | Creation paused, assignment paused, submission paused, verifyJob remains available, withdrawals remain possible, timeout refunds remain possible |
| **Provider binding** | Assigned provider succeeds, unassigned provider fails, wrong lease fails, stale leaseId after reassignment fails (LeaseMismatch), expired lease fails (LeaseExpired), proof after deadline fails (JobDeadlineExpired), relayer cannot change recipient, duplicate proof fails, backend rejects obsolete worker signature, contract payout uses current assignment provider |
| **Accounting invariants** | Job settles at most once, job never credits more than escrowed amount, only assigned provider can receive settlement, timeout-refunded job cannot later settle, `totalEscrowed` consistent, obligations never exceed contract balance, withdrawal cannot be re-entered |
| **Fuzz** | Amount fuzz, deadline boundary fuzz |
| **Invariant** | Escrow conservation, no double settle, earnings reconcile |

### 21.2 Backend Cryptographic Tests

These tests are separate from Solidity tests because the contract does not verify trace checkpoints or ECDSA signatures in the MVP.

| Category | Tests |
|---|---|
| **Golden vectors** | Valid proof passes all 12 checks |
| **Fingerprint tamper** | Changed model hash, changed input hash, changed config |
| **Checkpoint tamper** | Missing checkpoint, additional checkpoint, reordered checkpoint, modified checkpoint |
| **Output tamper** | Changed output bytes |
| **Signature tamper** | Wrong signer, wrong provider |
| **Freshness** | Expired proof |
| **Replay** | Reused lease, reused attempt, cross-job replay, cross-contract replay, cross-chain replay |
| **Encoding** | Malformed encoding, invalid UUID conversion, Python/Solidity encoding compatibility |

### 21.3 Backend Integration Tests

These tests exercise blockchain interaction, idempotent reconciliation, and the full verification-to-settlement flow.

| Category | Tests |
|---|---|
| **Idempotent reassignment** | Dropped assignProvider tx detected via receipt query, replacement tx submitted with controlled nonce, pending_chain lease activates on confirmed event, no new lease created while previous outcome uncertain, receipt-based reconciliation before resubmission |
| **Proof verification ordering** | Off-chain verify during Assigned state, submitProof after verdict persisted, verifyJob after confirmed ProofSubmitted, malformed proof fails attempt without contract call, cryptographically invalid proof committed and settled false |
| **Job price** | createJob transfers exactly jobPrice, setJobPrice reverts if zero or above maxJobAmount, setMaxJobAmount reverts if below current jobPrice, JobPriceUpdated event emitted correctly |
| **Event reconciliation** | Dropped ProofSubmitted event detected, dropped ProviderAssigned event detected, chain reorg handled, DB status updated from confirmed events only |

### 21.4 Enforcement Layer Summary

| Property | Enforced By |
|---|---|
| Job state transitions | Backend + Smart contract |
| Fund conservation | Smart contract |
| Double-settlement prevention | Smart contract |
| Fingerprint integrity | Backend (off-chain) |
| Checkpoint integrity | Backend (off-chain) |
| Merkle root integrity | Backend (off-chain) |
| EIP-712 signature verification | Backend (off-chain) |
| Replay protection | Backend (off-chain) + Smart contract (lease binding) |
| Pull-payment accounting | Smart contract |
| Timeout refund eligibility | Smart contract |
| Pause without fund trapping | Smart contract |
| Lease exclusivity | Database (partial unique index) + Row locking |
| Auth session revocation | Database + Backend |
| Rate limiting | Backend (slowapi) |
| Input validation | Backend + Worker |
| Model/input hash verification | Worker |

### 21.5 Manual Checks

- MetaMask approval and transaction states.
- Mobile and desktop dashboard layouts.
- New-provider setup on a clean Linux machine.
- R2 retention and signed URL expiry.
- Explorer links and testnet labeling.
- Recovery using the operator runbook.

---

## 22. Deployment Architecture

### GCP-copy deployment-profile amendment

**Decision date:** 2026-10-16

**Rationale:** the owner approved Cloud Run as the deployed FastAPI API host
for this separate GCP demonstration repository after GCP-001 established the
isolated adapter contract.

**Reversal condition:** switch the Vercel upstream back after the original
repository's canonical OCI host is available and independently passes health
and browser-auth acceptance, or after the owner approves a permanent provider
decision.

**Operating procedure:** [GCP Demo Host Runbook](runbooks/GCP_DEMO_HOST.md)

This amendment applies only to hosting and deployment in this GCP copy. OCI
remains canonical in the original repository. It does not revise Nebula's
protocol, security model, database schema, worker interface, contract network,
or deployment facts.

### 22.1 Free-Tier Stack

| Service | Purpose | Free Tier | Notes |
|---|---|---|---|
| Vercel | Frontend hosting | Unlimited projects | Auto-deploy on push |
| Google Cloud Run | Deployed public FastAPI demo API host | Usage-based allowance requires an active billing account | Request-based billing, minimum instances zero, low maximum instances, API only |
| Owner laptop | Demonstration worker and five controlled runners | Owner-operated | Started only for supervised tests/faculty demonstrations; never represented as continuously hosted |
| Supabase | PostgreSQL | 50k rows, 1GB | No credit card |
| Cloudflare R2 | Object storage | 10GB/mo, no egress | Confirm bucket exists |
| Upstash Redis | Cache/queue | 10k cmds/day | Optional, not required |
| Arbitrum Sepolia | Testnet blockchain | Free gas | Confirm RPC availability |
| Pinata IPFS | Optional pinning | 1GB free | Stretch only |
| Uptime Robot | Monitoring | 5 monitors | Confirm before deployment |

The temporary GCP demo profile is:

```text
Browser -> Vercel /api/v1/* -> public Cloud Run FastAPI /v1/*
                                -> Supabase PostgreSQL
                                -> Arbitrum Sepolia reads

Owner laptop during a supervised demonstration only
  -> deterministic fixture worker
  -> receipt, assignment, settlement, event, and reconciliation runners
  -> existing Arbitrum Sepolia contract interactions
```

Cloud Run must have `RUNNERS_ENABLED=false`, must receive no transaction-
signing key, and must not host a runner container, Cloud Run Job, scheduled
runner, worker pool, or keep-alive surrogate. This topology makes no continuous
hosted runners, no real GPU proof, no production SLA, and no production-readiness claim.

### 22.2 Environment Variables

All deployment-specific values come from environment variables. No hardcoded production domains. Custom domains are optional.

**Cloud Run API configuration (Secret Manager references for secrets):**
```bash
DATABASE_URL=postgresql://...          # Required
ARBITRUM_SEPOLIA_RPC=https://...       # Required
USDC_SEPOLIA_ADDRESS=0x...             # Required, verify on explorer
NEBULA_PAYMENT_CONTRACT=0x...          # Required, deployed contract address
R2_ACCOUNT_ID=...                      # Required
R2_ACCESS_KEY_ID=...                   # Required
R2_SECRET_ACCESS_KEY=...               # Required
R2_BUCKET_NAME=nebula-models           # Required
PINATA_API_KEY=...                     # Optional (stretch)
PINATA_API_SECRET=...                  # Optional (stretch)
JWT_SECRET=...                         # Required, min 32 chars
JWT_EXPIRY_HOURS=24                    # Required
JWT_REFRESH_EXPIRY_HOURS=168           # Required
FRONTEND_URL=https://...               # Required, CORS origin
RUNNERS_ENABLED=false                  # Required and immutable in GCP profile
```

`DATABASE_URL` and `JWT_SECRET` use owner-approved numbered Secret Manager
versions. No backend executor private key, worker signer, provider wallet key,
or service-account key is supplied to Cloud Run. Transaction-signing settings
remain only in the owner-controlled laptop runner environment and are never
copied into the GCP profile.

**Deployment blocker:** the current application still selects instance-local
`FileStorage`; declaring R2 environment values does not create a live durable
storage adapter. Cloud Run instances and the owner-laptop worker cannot share
that filesystem. The current GCP service contract also omits the complete
owner-approved public chain configuration. No GCP deployment or connected-flow
claim may proceed until a provider-neutral durable storage adapter and complete
runtime configuration contract pass local tests and review.

**Worker (.env):**
```bash
NODE_ID=<uuid>                         # From dashboard
API_KEY=sk_...                         # From dashboard
WORKER_PRIVATE_KEY=0x...               # Worker signing key (NOT wallet key)
BACKEND_URL=https://...                # Required
CUDA_VISIBLE_DEVICES=0                 # Optional
MODEL_CACHE_DIR=~/.nebula/models       # Optional
```

### 22.3 Deployment Checklist

- [ ] Contract deployed and verified on Arbiscan.
- [ ] Contract address, chain ID, and USDC address verified independently.
- [ ] A provider-neutral durable storage adapter is selected at the existing storage interface and is shared by Cloud Run and the owner-laptop worker; local `FileStorage` is rejected for the deployed profile.
- [ ] The complete secret/public runtime configuration inventory is validated before any cloud mutation.
- [ ] Owner approves the exact GCP project, region, billing account, and residual cost exposure.
- [ ] Budget alerts are active; owner records whether an eligible spend cap is accepted and understands its availability impact.
- [ ] Only the reviewed Cloud Run, Artifact Registry, and Secret Manager APIs are enabled; Cloud Build is enabled only if separately selected.
- [ ] Bootstrap, deployer, optional build, and runtime identities are separated; runtime has access only to exact required secrets.
- [ ] `DATABASE_URL` and `JWT_SECRET` exist as numbered Secret Manager versions; no value appears in Git, images, logs, or evidence.
- [ ] The reviewed backend image is scanned, recorded, and deployed by immutable digest.
- [ ] Cloud Run uses request-based billing, minimum instances zero, maximum instances two, and `RUNNERS_ENABLED=false`.
- [ ] Cloud Run contains only the FastAPI container and receives no chain-signing key or runner configuration.
- [ ] Public `/live` returns bounded `200`; database-backed `/ready` returns bounded `200` with approved Supabase and `503` when unavailable.
- [ ] The exact Cloud Run HTTPS origin is approved before materializing the Vercel `/api/v1/*` rewrite.
- [ ] A Vercel preview preserves same-origin browser requests and disables caching for authenticated API traffic.
- [ ] Real-browser verify, refresh rotation, logout, cookie flags/path, allowed Origin, and wrong/missing Origin checks pass before cutover.
- [ ] The previous Cloud Run revision, Vercel deployment, and canonical OCI switch-back route are recorded before exposure.
- [ ] CORS configured for frontend domain only.
- [ ] Rate limiting enabled.
- [ ] Database migrations applied.
- [ ] R2 bucket created with lifecycle policies (24h input expiry, 7d result expiry).
- [ ] Monitoring active (Uptime Robot health check).
- [ ] All UI payments labeled "testnet".
- [ ] No provider wallet private key stored on any worker.

---

## 23. MVP Roadmap

Each phase has a gate. The next phase does not begin until the current gate passes.

### Phase 0 — Reset the Baseline (Days 1–2)

**Deliverables:**
- Adopt this document as canonical.
- Record fixed formats for job IDs, fingerprint, result JSON, Merkle tree, and EIP-712 proof.
- Pin all dependency versions.
- Preserve useful scaffolding; identify code that must be replaced.

**Gate:** One documented golden PoAE vector exists, contract interface agreed, no task treats Redis, IPFS, four models, or cross-platform workers as blocking requirements.

### Phase 1 — Correct Escrow Contract (Week 1)

**Deliverables:**
- Enum-based state machine, pull payments, timeout refund, pause, `assignProvider`, `onlyVerifier submitProof`.
- Fixed contract-configured price (not user-provided amount).
- EIP-712 domain separator and typed-data structure defined.
- Foundry unit, fuzz, invariant, authorization, timeout, and reentrancy tests.
- Local deployment script and test token.

**Gate:** All fund-moving branches pass; escrow conservation invariant passes; unauthorized settlement and duplicate settlement fail.

### Phase 2 — Backend Workflow Foundation (Weeks 2–3)

**Deliverables:**
- 12-table database schema with constraints and enums.
- Wallet auth (challenge → verify → JWT → refresh → logout).
- Revocable node credentials with worker signer authorization.
- Private R2 upload/download with retention behavior.
- All four model registry entries with real artifact hashes.
- Escrow confirmation and contract event reconciliation.
- Database-backed scheduler with leases, row locking, retry, and exhaustion.

**Gate:** A test creates, escrows, queues, leases, expires, retries, and refunds a job without frontend or real inference.

### Phase 3 — Worker and PoAE Vertical Slice (Weeks 4–5)

**Deliverables:**
- Linux/NVIDIA worker polling and heartbeat.
- All four model adapters with fixed preprocessing.
- Deterministic fingerprint, fixed checkpoints, Merkle tree, and EIP-712 signing.
- 12-step proof verifier and idempotent settlement.
- Golden test vectors (10) and tamper cases (10).

**Gate:** Ten golden jobs produce expected proof commitments; every required tamper vector fails; one real GPU job settles correctly on local chain and Arbitrum Sepolia staging.

### Phase 4 — Thin Usable Frontend (Week 6)

**Deliverables:**
- MetaMask authentication with refresh flow.
- User submission, escrow, job list, result, PoAE, and refund views.
- Provider registration, node status, credential rotation, and earnings views.
- Polling and complete loading/error/transaction states.

**Gate:** A new user and provider can complete the happy path using only documented setup instructions.

### Phase 5 — Failure Handling and Integration (Weeks 7–8)

**Deliverables:**
- Worker death, lease timeout, retry, invalid proof, refund, backend restart, and RPC recovery flows.
- Ownership, rate-limit, upload, credential-revocation, and secret-leakage tests.
- Contract/database reconciliation command and operator runbook.
- CI for contract, backend, worker, frontend, migrations, and end-to-end tests.

**Gate:** All launch success criteria pass in staging with no open critical or high-severity defect.

### Phase 6 — Public MVP and Evaluation (Weeks 9–10)

**Deliverables:**
- In this GCP copy: Vercel frontend, Cloud Run API-only demo host, Supabase PostgreSQL, private R2, and the existing Arbitrum Sepolia deployment; the owner laptop supplies the worker and five controlled runners during each demonstration.
- Monitoring, readiness checks, structured logs, backup/restore check, and smoke test.
- Public README, worker guide, architecture diagram, PoAE limitations disclosure, and demonstration script.
- Small beta with at least five users and one external provider.

**Gate:** Ten consecutive public jobs complete, tamper/refund demo succeeds, contract and database reconcile, and a new participant completes the documented flow without developer intervention.

### Phase 7 — Polish and Launch (Weeks 11–12)

**Deliverables:**
- Bug fixes from beta feedback.
- Cross-browser and mobile testing.
- Final documentation review.
- Public announcement.

### Post-Gate Stretch Sequence

1. Add a second GPU worker and demonstrate parallel leases.
2. Add YOLOv5 through a complete model-specific adapter and golden vectors (already required in v3.1).
3. Add optional IPFS publication for explicit non-sensitive results.
4. Add Redis only when measured database queue contention justifies it.
5. Add WebSockets only when polling creates a measured user or capacity problem.
6. Evaluate BERT, Whisper, Windows, and macOS independently.

---

## 24. Known Limitations

1. **Uptime:** Not 99%. The Cloud Run demo API can scale to zero, cold-start, be throttled by quotas or cost controls, and depend on Supabase and the owner laptop. There is no production SLA.
2. **Concurrency:** The Cloud Run demo profile is capped at a low maximum instance count for blast-radius control; it is not a throughput or cost guarantee and must be established by load testing.
3. **Single verifier:** The backend is the sole verifier. If the backend is compromised, incorrect verdicts can be authorized.
4. **PoAE does not prove GPU execution:** Workers can fabricate internally consistent hashes. The guarantee is tamper-evidence, not correctness.
5. **Storage:** Cloudflare R2 has 10GB/month free. Sufficient for MVP.
6. **Database:** Supabase free tier has 50,000 rows. Sufficient for thousands of jobs.
7. **Payments:** Fixed pricing only. No dynamic pricing based on demand.
8. **Decentralization:** Backend controls scheduling. Blockchain handles escrow and settlement only.
9. **Security:** Workers trust the backend for job assignments. No code signing.
10. **Network:** Assumes reasonable internet. Slow networks may cause timeouts.
11. **Support:** Community-driven. No SLA or guaranteed uptime.
12. **Proof overhead:** Inference latency increases ~10–15% due to checkpoint hashing and Merkle tree construction.
13. **Simplified PoAE:** Uses a single verifier (backend). Future: multiple independent verifiers with stake.
14. **No on-chain signature verification:** Gas too high. Signatures verified off-chain in backend.
15. **Input/result privacy:** Inputs and results are visible to the provider during inference (standard for non-confidential compute).

---

## 25. Post-MVP Work

| Feature | Why Deferred |
|---|---|
| ZKML proofs | Requires significant cryptographic infrastructure |
| TEE attestation | Requires specific hardware and SDK integration |
| Staking and slashing | Requires economic design and mainnet token |
| Decentralized verifier network | Requires multi-party consensus design |
| Optimistic disputes | Requires fraud-proof mechanism |
| WebSocket updates | Polling sufficient for MVP user counts |
| Dynamic pricing | Requires demand modeling |
| Reputation system | Requires longitudinal data |
| Mainnet deployment | Requires security audit and real-value considerations |
| Arbitrary model uploads | Requires sandboxing and security review |
| Windows/macOS worker | Requires cross-platform testing |
| Notifications (Discord/Telegram) | Requires webhook integration |
| Redis queueing | Requires measured justification |
| IPFS publication | Added as optional stretch |
| Export CSV, View Logs, Rotate API Key UI | Minor UX features |

---

## 26. Acceptance Criteria

The MVP is ready for demonstration when ALL of the following pass:

| # | Criterion |
|---|---|
| 1 | 10 consecutive jobs complete successfully across all 4 models |
| 2 | At least one external Linux/NVIDIA worker completes jobs |
| 3 | Two workers complete and receive separate jobs (if hardware available) |
| 4 | 100% of defined tampered proof cases are rejected |
| 5 | Cross-job, cross-lease, cross-contract, and cross-chain replays fail |
| 6 | No duplicate provider credit or refund in any test |
| 7 | A killed worker's lease expires and the job is retried or refunded |
| 8 | Unauthorized users cannot download another user's input, result, or proof |
| 9 | Contract and database recover after a simulated dropped transaction |
| 10 | A new user and provider complete the documented flow without code changes |
| 11 | Timeout refund works correctly (refund after deadline, revert before) |
| 12 | Pull payments work correctly (withdraw, reentrancy blocked) |
| 13 | Pause emergency works without trapping funds |
| 14 | All 10 golden test vectors pass |
| 15 | API p95 below 750ms excluding files, inference, and blockchain confirmation |

---

## 27. Migration Notes from v3.0

### 27.1 What Changed

| Area | v3.0 | v3.1 | Reason |
|---|---|---|---|
| Contract state | Booleans (`completed`, `verified`, `proofValid`) | Explicit `JobState` enum | Prevents invalid state combinations |
| submitProof | Provider or owner can call | `onlyVerifier` only (backend submits) | Prevents unauthorized provider claiming |
| Settlement | Direct `usdc.transfer` in `verifyJob` | Pull payments via `pendingWithdrawals` + `withdraw()` | Prevents failed-transfer fund trapping |
| Timeout refund | None | `requestTimeoutRefund` after `jobDeadline` | Prevents permanent fund lock |
| Pause | None | Partial: `createJob`/`assignProvider`/`submitProof` paused; `verifyJob`/`withdraw`/`requestTimeoutRefund` always available | Emergency without fund trapping |
| Fingerprint | `pickle(model.state_dict()) + datetime` | Deterministic: domain separator + model/input hashes | Reproducible, verifiable, no runtime dependence |
| Signature | EIP-191 `merkle_root:job_id:timestamp` | EIP-712 typed-data with 12 fields | Prevents 8+ replay vectors |
| Job ID | `bytes32(bytes(jobIdStr))` truncation | UUID → 16 bytes → bytes32 (documented zero-padding) | Deterministic, reversible, no collision |
| Provider binding | Any address can be passed as `provider` | Fixed by `assignProvider()`, cannot change during proof | Prevents provider substitution |
| Time boundaries | None | `jobDeadline` (24hr) + `leaseExpiresAt` (1hr) | Allows lease retry while job remains active |
| Database | 5 tables | 12 tables | Supports leases, attempts, proofs, auth, chain tracking |
| Privacy | Results to IPFS + public R2 by default | Private R2 default, IPFS optional stretch | Prevents unintended data exposure |
| PoAE claims | "Cryptographically impossible to hide" | "Signed tamper-evident attestation, not proof of correct inference" | Honest disclosure |
| Checkpoints | Dynamic `model.children()` traversal | Fixed named checkpoints per model adapter | Deterministic, reproducible |
| Worker key | Wallet private key on worker | Separate secp256k1 signing key | Provider wallet never on worker |
| API paths | `/v1/jobs/{id}/confirm-blockchain`, `/v1/jobs/{id}/complete` | `/v1/jobs/{id}/confirm-escrow`, `/v1/worker/leases/{id}/complete` | Consistent with lease model |
| Redis | Required | Optional | Not required for MVP |
| WebSocket | Listed as endpoint | Post-MVP | Polling sufficient |
| maxJobAmount | Not specified | 10 USDC (10_000_000 base units), owner-adjustable | Limits testnet operational risk |
| max_attempts | Not specified | Default 3, allows two retries before refund | Balances reliability against stuck jobs |
| Merkle algorithm | `MerkleTools` with `do_hash=False` (library default) | Canonical: SHA256(0x00 || leaf), SHA256(0x01 || left || right), odd-node duplication | Deterministic, library-independent, golden-vector-verifiable |
| submitProof params | `(jobId, merkleRoot, outputHash, provider)` | `(jobId, leaseId, merkleRoot, outputHash)` — no provider param | Contract validates leaseId match; stale proofs rejected on-chain |
| Lease management | Single assignment, no reassignment | Initial + reassignment with guards; idempotent blockchain reconciliation | Prevents stale lease proof acceptance; supports retry without fund trapping |
| JobState enum | Included `Cancelled` | Removed `Cancelled`; pre-escrow DB expiry uses `expired_pre_escrow` | No on-chain cancel function; recovery via timeout refund |
| DB statuses | `cancelled` | `expired_pre_escrow` (terminal), `retry_pending`, `attempts_exhausted`, `awaiting_timeout_refund` | Distinguishes DB-only states from on-chain finalized states |
| Lease status | `active`, `expired`, `completed`, `failed` | Added `pending_chain`; unique index covers active OR pending_chain | Supports idempotent blockchain reconciliation |
| Custom errors | — | Added `LeaseMismatch`, `JobDeadlineExpired`, `InvalidJobPrice` | Explicit error codes for lease, deadline, and price validation |
| Job pricing | User-specified amount | Contract-configured `jobPrice` (default 50,000 base units / 0.05 USDC) | All 4 MVP models use same on-chain price; `setJobPrice()` owner-controlled; `setMaxJobAmount()` must not go below current price |

### 27.2 What Preserved

- 4-model MVP scope (ResNet50, YOLOv5, BERT-Base, Whisper Tiny)
- IPFS publication (moved to optional stretch)
- Fixed per-model pricing
- Private Cloudflare R2 storage
- Arbitrum Sepolia testnet
- FastAPI backend
- React frontend on Vercel
- FastAPI deployed as an API-only Cloud Run demo host in this GCP copy; OCI remains canonical in the original repository
- Owner-laptop worker and controlled runners during demonstrations; no continuous hosted runner claim
- Python worker on GPU nodes
- Centralized backend scheduler
- Backend-operated verification
- $0 free-tier budget

---

## 28. Decision Log

| # | Decision | Reason | Security Consequence | MVP Tradeoff |
|---|---|---|---|---|
| 1 | UUID everywhere with canonical bytes32 encoding | Deterministic, reversible, no collision, single identity across all layers | Prevents ID mismatch between contract and DB | Slightly more complex than truncation |
| 2 | Backend-established deterministic fingerprint | Worker cannot compute a favorable fingerprint; backend verifies integrity | Prevents fingerprint manipulation | Backend must compute before escrow, adds latency |
| 3 | EIP-712 typed-data proof envelope | Prevents cross-chain, cross-contract, cross-job, cross-lease, cross-attempt replay | 8+ replay vectors blocked | More complex than EIP-191 string signing |
| 4 | Provider assignment before proof submission | Only the backend-assigned provider can submit proof for a job | Prevents unauthorized providers claiming payment | Extra `assignProvider` call on-chain |
| 5 | Separate job deadline and lease expiry | Lease can expire and retry while job remains active; prevents fund trapping | Flexible retry without permanent lock | Two time boundaries to manage |
| 6 | Pull-payment settlement | No failed-transfer fund trapping; users/providers control withdrawal timing | Atomic state changes, reentrancy protection | Extra `withdraw()` step (worse UX, better safety) |
| 7 | Partial pause behavior | Emergency pause without trapping user funds; withdrawals always available | Users never lose access to credited funds | More nuanced than blanket pause |
| 8 | Private-by-default R2 storage | No unintended data exposure; user privacy preserved | No immutable audit trail by default | IPFS becomes opt-in stretch |
| 9 | Separate worker signing key | Provider wallet never enters worker configuration; compromised worker doesn't expose wallet | Better key isolation | Extra key management step for providers |
| 10 | Fixed named checkpoints per adapter | Deterministic, reproducible, no runtime discovery | Consistent checkpoint hashes across runs | More code per model adapter |
| 11 | Event listener + reconciliation polling | Handles dropped RPC responses, chain reorganizations, idempotent ingestion | Contract and DB stay synchronized | Backend complexity |
| 12 | 24h access + 7d refresh tokens with rotation | Short-lived access limits token theft window; rotation detects reuse | Stolen tokens quickly expire; reuse detection enables revocation | More complex auth flow |
| 13 | Worker credentials separate from user sessions | Workers authenticate with API keys, not JWT; different trust domains | Compromised worker doesn't affect user sessions | Two auth mechanisms to maintain |
| 14 | Honest PoAE security disclosure | Accurate claims prevent misuse and academic dishonesty | Clear trust model for evaluators | Less impressive marketing language |
| 15 | Default maxJobAmount = 10 USDC (10_000_000 base units) | Limits testnet operational risk; owner can adjust via setMaxJobAmount() | Caps maximum per-job escrow; prevents accidental large locks | Low cap may require adjustment for future models |
| 16 | Default max_attempts = 3 | Allows two retries before refund; balances reliability against stuck jobs | Three attempts gives worker failure recovery; exhaustion triggers refund | More attempts delay refund on persistent failure |
| 17 | Canonical Merkle algorithm with 0x00/0x01 prefix and odd-node duplication | Deterministic, reproducible, library-independent; prevents second-preimage attacks | Backend and worker produce identical roots; golden vectors verify correctness | Requires custom implementation instead of off-the-shelf library |
| 18 | Four-parameter submitProof with leaseId validation | Contract rejects proofs from reassigned or expired leases on-chain | Prevents stale lease proof acceptance without backend trust | More complex than three-parameter submitProof |
| 19 | Idempotent blockchain reconciliation for lease assignment | Persist tx hash and nonce; query receipt before resubmitting; activate on confirmed event only | Prevents duplicate chain transactions and double-assignment | More complex scheduler logic |
| 20 | expired_pre_escrow as sole DB-only terminal status | Pre-escrow DB records expire without on-chain state; no Cancelled in Solidity enum | Clean separation of DB workflow from contract state | Users must wait for DB expiry on abandoned pre-escrow jobs |
| 21 | Contract-configured jobPrice (default 50,000 base units) | All 4 MVP models use same on-chain price; avoids per-model pricing complexity in contract | Simpler contract; owner can adjust price via setJobPrice(); setMaxJobAmount enforces floor | Per-model pricing deferred to Post-MVP |

---

## 29. Glossary

| Term | Definition |
|---|---|
| **Job** | One request to run one approved model version against one exact input for one fixed testnet price |
| **GPU provider** | Wallet-identified participant that operates one or more GPU nodes |
| **GPU node** | Provider-operated machine registered to receive jobs |
| **Worker** | Nebula software process running on a GPU node |
| **Worker signer** | Node-specific signing identity authorized by the GPU provider, used to sign proof envelopes |
| **Lease** | Time-bounded exclusive assignment of a job to one GPU node |
| **Job fingerprint** | Deterministic hash binding protocol version, model identity, model artifact, preprocessing version, and input |
| **Checkpoint** | Named model-specific point whose intermediate tensor is hashed |
| **Execution trace** | Ordered checkpoint names and hashes for one inference |
| **Proof envelope** | Versioned worker-signed package containing job fingerprint, execution trace commitment, output hash, and job-binding metadata |
| **PoAE proof** | User-facing name for the proof envelope; not a zero-knowledge proof |
| **Verifier** | Trusted backend role that validates proof envelopes and authorizes settlement |
| **Verdict** | Terminal `VALID` or `INVALID` decision for a job's proof envelope |
| **Settlement** | Single terminal escrow outcome crediting either provider earnings or a user refund |
| **Pull payment** | Payment credited to a pending balance; recipient calls `withdraw()` to claim |
| **Chain job ID** | UUID converted to bytes32 for on-chain storage |
| **Base units** | Integer representation of USDC amounts (6 decimals); e.g., 0.05 USDC = 50,000 base units |
| **Domain separator** | EIP-712 value binding the proof envelope to a specific chain, contract, and protocol version |
| **Idempotency key** | UUID provided by the client to prevent duplicate processing of retryable requests |
| **Row locking** | PostgreSQL `SELECT ... FOR UPDATE` ensuring only one scheduler instance can assign a job |

---

*End of document. This is the canonical specification for Nebula AI Cloud MVP v3.1.*
