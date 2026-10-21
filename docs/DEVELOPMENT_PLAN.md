# Nebula AI Cloud - Development Plan

**Canonical specification:** `docs/NEBULA_PRD_v3.1.md`
**Timeline:** 12 weeks (3 months)
**Developer:** 1 person (intermediate level)
**Strategy:** Sequential phases with worker parallelized, smart contract first, full scope preserved

---

## Phase 0: Project Scaffolding & Setup (Day 1)

**Goal:** Create the complete project structure so every component has a home.

### Tasks
- [ ] Create directory structure (see below)
- [ ] Initialize Git repo
- [ ] Create root `README.md`
- [ ] Create `.gitignore`
- [ ] Create `.env.example` templates for each component
- [ ] Set up Foundry project (`foundry.toml`)
- [ ] Set up FastAPI project (`pyproject.toml` or `requirements.txt`)
- [ ] Set up React project (`package.json` via Vite)
- [ ] Set up Worker project (`requirements.txt`)

### Directory Structure
```
nebula-ai/
├── README.md
├── .gitignore
├── .env.example
├── docs/
│   ├── NEBULA_PRD_v3.1.md          # Canonical specification
│   └── DEVELOPMENT_PLAN.md
├── contracts/                       # Solidity + Foundry
│   ├── foundry.toml
│   ├── src/
│   │   └── NebulaVerifiableAI.sol
│   ├── test/
│   │   └── NebulaVerifiableAI.t.sol
│   ├── script/
│   │   └── Deploy.s.sol
│   └── lib/                         # OpenZeppelin (forge install)
├── backend/                         # FastAPI
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI app entry
│   │   ├── config.py                # Settings / env vars
│   │   ├── database.py              # Supabase/PostgreSQL connection
│   │   ├── models/                  # SQLAlchemy models (grouped by domain)
│   │   │   ├── __init__.py
│   │   │   ├── auth.py              # users, auth_challenges, auth_sessions
│   │   │   ├── job.py               # jobs, job_attempts, proofs, leases
│   │   │   ├── node.py              # nodes
│   │   │   ├── payment.py           # payments, chain_transactions, blockchain_events
│   │   │   └── model.py             # supported_models
│   │   ├── schemas/                 # Pydantic schemas
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── node.py
│   │   │   ├── job.py
│   │   │   └── model.py
│   │   ├── routers/                 # API endpoints
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── nodes.py
│   │   │   ├── models.py
│   │   │   ├── jobs.py
│   │   │   ├── earnings.py
│   │   │   └── health.py
│   │   ├── services/                # Business logic
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py
│   │   │   ├── scheduler.py         # Lease management, retry, idempotent reconciliation
│   │   │   ├── lease_manager.py     # Lease lifecycle, pending_chain → active
│   │   │   ├── attempt_manager.py   # Attempt tracking, exhaustion handling
│   │   │   ├── proof_verifier.py    # 12-step verification
│   │   │   ├── blockchain_service.py
│   │   │   ├── blockchain_listener.py
│   │   │   ├── reconciliation.py    # Contract vs DB state comparison
│   │   │   └── storage_service.py   # R2 only (IPFS optional Post-MVP)
│   │   ├── middleware/
│   │   │   ├── __init__.py
│   │   │   ├── rate_limit.py
│   │   │   └── cors.py
│   │   └── security.py
│   ├── migrations/
│   │   └── 001_initial_schema.sql   # 12 tables, all constraints
│   └── tests/
│       ├── __init__.py
│       ├── test_auth.py
│       ├── test_jobs.py
│       ├── test_scheduler.py
│       ├── test_proof_verifier.py
│       └── test_reconciliation.py
├── frontend/                        # React + Vite
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   ├── public/
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── vite-env.d.ts
│       ├── api/                     # API client
│       │   ├── client.ts
│       │   ├── auth.ts
│       │   ├── jobs.ts
│       │   ├── nodes.ts
│       │   └── models.ts
│       ├── components/              # Reusable UI
│       │   ├── Layout.tsx
│       │   ├── Navbar.tsx
│       │   ├── WalletConnect.tsx
│       │   ├── JobCard.tsx
│       │   ├── NodeCard.tsx
│       │   └── ModelSelector.tsx
│       ├── pages/                   # Route pages
│       │   ├── Home.tsx
│       │   ├── provider/
│       │   │   ├── Dashboard.tsx
│       │   │   ├── RegisterNode.tsx
│       │   │   └── Earnings.tsx
│       │   └── user/
│       │       ├── Dashboard.tsx
│       │       ├── SubmitJob.tsx
│       │       └── JobDetail.tsx
│       ├── hooks/                   # Custom React hooks
│       │   ├── useWallet.ts
│       │   ├── useJobs.ts
│       │   └── useNodes.ts
│       ├── contracts/               # ABI imports
│       │   └── NebulaVerifiableAI.ts
│       ├── styles/
│       │   └── globals.css
│       └── utils/
│           ├── constants.ts
│           └── helpers.ts
├── worker/                          # Python GPU worker
│   ├── requirements.txt
│   ├── setup.py                     # Setup wizard
│   ├── worker.py                    # Main entry point
│   ├── config.py                    # Settings / env vars
│   ├── core/
│   │   ├── __init__.py
│   │   ├── executor.py              # Job execution logic
│   │   ├── model_loader.py          # Model download + cache
│   │   ├── preprocessor.py          # Model-specific input preprocessing
│   │   └── tracer.py                # Fixed checkpoint execution trace
│   ├── proof/
│   │   ├── __init__.py
│   │   ├── fingerprint.py           # Deterministic domain-separator fingerprint
│   │   ├── merkle.py                # Canonical Merkle algorithm (0x00/0x01 prefix)
│   │   └── signer.py                # EIP-712 typed-data signing
│   ├── storage/
│   │   ├── __init__.py
│   │   └── r2_upload.py             # Result upload to R2
│   └── tests/
│       ├── __init__.py
│       ├── test_executor.py
│       ├── test_preprocessor.py
│       ├── test_proof.py
│       └── test_merkle.py           # Golden vector tests
└── scripts/                         # Deployment & utility scripts
    ├── deploy-contract.sh
    ├── deploy-backend.sh
    ├── deploy-frontend.sh
    └── upload-models.sh
```

---

## Phase 1: Smart Contract (Week 1-2)

**Goal:** Deploy `NebulaVerifiableAI` to Arbitrum Sepolia, verified on explorer.

**PRD v3.1 sections:** 11 (Smart Contract Specification), 12 (Payment, Withdrawal, and Refund Accounting)

### Week 1: Build & Test Locally
- [ ] Initialize Foundry project: `forge init contracts`
- [ ] Install OpenZeppelin: `forge install OpenZeppelin/openzeppelin-contracts`
- [ ] Write `NebulaVerifiableAI.sol` per PRD v3.1 Section 11.1:
  - `JobState` enum: `{ None, Created, Assigned, ProofSubmitted, Settled, Refunded }` (no Cancelled)
  - `createJob(bytes32 chainJobId, bytes32 fingerprint)` — user-funded escrow via `safeTransferFrom`, transfers exactly `jobPrice`
  - `assignProvider(bytes32 jobId, address provider, bytes32 leaseId, uint64 leaseExpiresAt)` — initial (Created→Assigned) and reassign (Assigned→Assigned) with guards
  - `submitProof(bytes32 jobId, bytes32 leaseId, bytes32 merkleRoot, bytes32 outputHash)` — onlyVerifier, validates leaseId match, lease not expired, deadline not expired
  - `verifyJob(bytes32 jobId, bool isValid)` — onlyVerifier, pull-payment settlement
  - `requestTimeoutRefund(bytes32 jobId)` — job creator only, after deadline
  - `withdraw()` — CEI pattern, nonReentrant
  - `setMaxJobAmount(uint256 _max)` — require _max >= jobPrice, emit MaxJobAmountUpdated
  - `setJobPrice(uint256 _price)` — require 0 < _price <= maxJobAmount, emit JobPriceUpdated
  - Events: `JobCreated`, `ProviderAssigned`, `ProofSubmitted(jobId, leaseId, merkleRoot, outputHash, provider)`, `JobSettled`, `PaymentCredited`, `WithdrawalCompleted`, `TimeoutRefundCredited`, `VerifierUpdated`, `MaxJobAmountUpdated`, `JobPriceUpdated`
  - Custom errors: `InvalidUSDC`, `InvalidVerifier`, `InvalidAmount`, `InvalidJobID`, `InvalidFingerprint`, `InvalidMerkleRoot`, `InvalidOutputHash`, `JobAlreadyExists`, `JobNotFound`, `JobNotInState`, `NotJobCreator`, `NotAssignedProvider`, `OnlyVerifier`, `LeaseExpired`, `LeaseMismatch`, `JobDeadlineExpired`, `ProofAlreadySubmitted`, `NoProofSubmitted`, `AmountExceedsMax`, `InvalidJobPrice`, `RefundTooEarly`, `RefundAlreadyProcessed`, `WithdrawInsufficient`, `TransferFailed`
  - Constants: `JOB_DEADLINE_SECONDS = 24 hours`, `LEASE_DURATION_SECONDS = 1 hour`
  - Accounting: `totalEscrowed`, `totalPendingWithdrawals`, `pendingWithdrawals` mapping
  - MaxJobAmount default: 10e6 (10 USDC), jobPrice default: 50_000 (0.05 USDC)
- [ ] Write comprehensive Foundry tests:
  - **State machine:** Every valid transition, every invalid transition, duplicate creation, duplicate proof, duplicate settlement, settlement after refund, refund after settlement
  - **submitProof lease validation:** Valid proof with correct leaseId succeeds, stale leaseId reverts (LeaseMismatch), expired lease reverts (LeaseExpired), proof after jobDeadline reverts (JobDeadlineExpired), proof from reassigned lease reverts
  - **Lease reassignment:** Initial assignment from Created, reassignment after lease expiry (state stays Assigned), reassignment before expiry reverts, reassignment after jobDeadline reverts (JobDeadlineExpired), reassignment with same lease ID reverts, reassignment from ProofSubmitted reverts, reassignment from terminal state reverts
  - **Job price:** createJob transfers exactly jobPrice, setJobPrice reverts if zero or above maxJobAmount, setMaxJobAmount reverts if below current jobPrice, JobPriceUpdated event emitted correctly
  - **Attempt exhaustion:** Exhaustion does not call contract, exhaustion prevents new backend leases, timeout refund succeeds after exhausted attempts, timeout refund reverts before deadline
  - **Pull payments:** Provider withdrawal, user refund withdrawal, zero-balance withdrawal, multiple credited jobs, failed token transfer, reentrancy attempt, accounting totals
  - **Timeout:** Refund strictly after deadline, revert before deadline, exact deadline boundary, refund after verifier outage, settlement/timeout race, duplicate timeout request
  - **Pause:** Creation paused, assignment paused, submission paused, verifyJob remains available, withdrawals remain possible, timeout refunds remain possible
  - **Provider binding:** Assigned provider succeeds, unassigned provider fails, wrong lease fails, stale leaseId after reassignment fails (LeaseMismatch), expired lease fails (LeaseExpired), proof after deadline fails (JobDeadlineExpired), relayer cannot change recipient, duplicate proof fails, backend rejects obsolete worker signature, contract payout uses current assignment provider
  - **Accounting invariants:** Job settles at most once, job never credits more than escrowed amount, only assigned provider can receive settlement, timeout-refunded job cannot later settle, `totalEscrowed` consistent, obligations never exceed contract balance, withdrawal cannot be re-entered
  - **Fuzz:** Amount fuzz, deadline boundary fuzz (256 runs)
  - **Invariant:** Escrow conservation, no double settle, earnings reconcile (4 invariants, 256 runs each)
- [ ] Run `forge test --gas-report` — all green
- [ ] Run `forge snapshot` — gas snapshots

### Week 2: Deploy & Verify
- [ ] Get Arbitrum Sepolia ETH from faucet
- [ ] Get testnet USDC from Circle faucet
- [ ] Write deployment script `Deploy.s.sol`
- [ ] Deploy: `forge create --rpc-url $RPC --private-key $KEY --constructor-args $USDC_ADDR`
- [ ] Verify on Arbiscan: `forge verify-contract`
- [ ] Save contract address to `.env`
- [ ] Test contract interaction from a script (create job, assign provider, submit proof, verify)

### Deliverables
- `contracts/src/NebulaVerifiableAI.sol` — complete, tested, matching PRD v3.1 Section 11.1
- `contracts/test/NebulaVerifiableAI.t.sol` — full test coverage per PRD v3.1 Section 21.1
- Contract deployed and verified on Arbitrum Sepolia

---

## Phase 2: Backend API Foundation (Week 2-4)

**Goal:** Working FastAPI with auth, node registration, model registry, and 12-table database.

**PRD v3.1 sections:** 13 (Backend Architecture), 15 (API Endpoints), 16 (Authentication)

### Week 2-3: Project Setup + Database
- [ ] Initialize FastAPI project with `uvicorn`
- [ ] Set up `pyproject.toml` with dependencies:
  - `fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`
  - `pydantic`, `python-jose[cryptography]`, `eth-account`, `boto3` (for R2)
  - `httpx`, `python-multipart`, `slowapi`
- [ ] Create `app/config.py` — Pydantic Settings from env vars
- [ ] Create `app/database.py` — async SQLAlchemy engine + session
- [ ] Write migration `001_initial_schema.sql` per PRD v3.1 Section 16 — all 12 tables:
  - `users` — wallet address, role, display name
  - `supported_models` — model ID, name, version, price_base_units, VRAM requirement
  - `nodes` — provider ID, GPU info, status, last_heartbeat, signer address
  - `jobs` — user_id, model_id, chain_job_id, status (14-value CHECK), assigned_node_id, current_lease_id, deadline, max_attempts, current_attempt, expected_fingerprint, price_base_units
  - `payments` — job_id, user_id, provider_id, amount, status
  - `auth_challenges` — wallet, challenge, nonce, expiry
  - `auth_sessions` — user_id, access token hash, refresh token hash, expiry
  - `leases` — job_id, node_id, lease_id, status (`pending_chain`/`active`/`expired`/`completed`/`failed`), tx_hash, nonce, heartbeat_at, expires_at
  - `job_attempts` — job_id, node_id, lease_id, attempt_number, status, fingerprint_hash, merkle_root, output_hash, signature
  - `proofs` — job_attempt_id, protocol_version, fingerprint_hash, merkle_root, output_hash, signature, timestamp
  - `chain_transactions` — chain_id, contract_address, job_id, tx_hash, tx_type, from/to addresses, amount, block number
  - `blockchain_events` — chain_id, contract_address, event_name, job_id, block number, tx hash, parsed data
  - All indexes, constraints, and enums per PRD v3.1
  - `NUMERIC(78,0)` for all monetary amounts (no floating-point or DECIMAL(10,2))
- [ ] Run migration against Supabase
- [ ] Seed `supported_models` table with 4 models from PRD v3.1:
  - YOLOv5 ($0.05), BERT-Base ($0.03), ResNet50 ($0.05), Whisper Tiny ($0.10)

### Week 3: Auth + Node Registration
- [ ] `POST /v1/auth/challenge` — generate random message for wallet to sign
- [ ] `POST /v1/auth/verify` — verify signature, return JWT (24h) + refresh token (7d)
- [ ] `POST /v1/auth/refresh` — refresh expired access token
- [ ] Auth middleware — extract user from JWT, inject into request
- [ ] `POST /v1/nodes` — register GPU node (creates DB record, generates API key)
- [ ] `GET /v1/nodes` — list active nodes (public)
- [ ] `GET /v1/nodes/{node_id}` — node details (public)
- [ ] `POST /v1/worker/heartbeat` — worker heartbeat (updates last_heartbeat in DB only; NO contract call, NO lease extension)
- [ ] `GET /v1/models` — list supported models (public)
- [ ] `GET /v1/models/{model_id}/signed-url` — generate presigned R2 URL (5min expiry)
- [ ] `GET /v1/health/live` and `/v1/health/ready` — health checks

### Week 4: Security + Rate Limiting
- [ ] Implement `security.py`:
  - `validate_input_file()` — size + MIME type check
  - `verify_wallet_signature()` — using `eth_account`
- [ ] Implement rate limiting with `slowapi`:
  - 100 req/15min per IP (global)
  - 5 jobs/min per user
  - 10 auth/min per IP
- [ ] CORS middleware — allow only `FRONTEND_URL`
- [ ] Input validation on all endpoints

### Deliverables
- `backend/app/` — complete FastAPI application per PRD v3.1 Section 13
- All auth, node, model endpoints working
- 12-table database schema deployed to Supabase
- Rate limiting + CORS configured

---

## Phase 3: Backend API Core (Week 4-6)

**Goal:** Job submission flow with user-funded escrow, scheduler with idempotent lease management, proof verification, blockchain integration.

**PRD v3.1 sections:** 13.1 (Job Lifecycle), 13.3 (Scheduler), 13.4 (Storage), 13.5 (Proof Verifier), 13.6 (Blockchain Service), 13.7 (Reconciliation)

### Week 4-5: Job Submission + Scheduler
- [x] `POST /v1/jobs` — create pre-escrow job:
  - Validate model exists, file size within limits
  - Generate UUID, compute deterministic fingerprint per PRD v3.1 Section 8.2
  - Upload input to R2 (presigned URL, 24h expiry)
  - Create DB record (status: `pending_blockchain`)
  - Return `{job_id, chainJobId, fingerprint, model_id, price_base_units}`
- [x] `POST /v1/jobs/{id}/confirm-escrow` — confirm blockchain escrow:
  - Verify tx receipt on-chain: correct sender, contract address, chain ID, event fields, escrow amount
  - Update status to `queued`
  - Store `blockchain_job_id` (bytes32 hex)
  - If pre-escrow record abandoned (no confirm within timeout): set status → `expired_pre_escrow` (terminal, on-chain state remains None)
- [x] `GET /v1/jobs` — list user's jobs (authenticated)
- [x] `GET /v1/jobs/{id}` — job details + results
- [x] Scheduler service (PRD v3.1 Section 13.3):
  - Query eligible jobs (`state = 'Created'` and no active/pending_chain lease)
  - Row locking (`SELECT ... FOR UPDATE`) for concurrent safety
  - Filter nodes: status='online', vram >= model requirement, heartbeat < 90s
  - Select least loaded node (fewest active leases)
  - Create lease record with status = `pending_chain`, persist tx_hash and nonce
  - Call `assignProvider()` on contract
  - On confirmed `ProviderAssigned` event: set lease.status = `active`, update job → `assigned`
  - On failed tx: log error, leave lease as `pending_chain`, retry next cycle
  - Idempotent blockchain reconciliation: query receipt, activate if confirmed, resubmit only if dropped (controlled nonce), never create new lease while previous outcome uncertain
  - Check for expired leases: mark expired, increment current_attempt
  - If current_attempt < max_attempts: set `retry_pending`, clear DB refs, create new lease (`pending_chain`) and attempt, call reassignment path
  - If current_attempt >= max_attempts: set `attempts_exhausted`, no contract call
- [x] `POST /v1/worker/leases/next` — acquire next compatible lease
- [x] `POST /v1/worker/leases/{id}/ack` — acknowledge lease before download
- [x] `POST /v1/worker/leases/{id}/result-upload` — presigned R2 upload for result
- [x] `POST /v1/worker/leases/{id}/complete` — worker submits EIP-712 proof envelope
- [x] `POST /v1/worker/leases/{id}/fail` — report attempt failure

### Week 5-6: Proof Verification + Blockchain
- [x] `ProofVerifier` service (12-step verification per PRD v3.1 Section 9.4):
  1. Validate protocol version
  2. Validate job state == `ProofSubmitted`
  3. Validate job exists and is in valid state
  4. Rebuild EIP-712 domain separator
  5. Reconstruct ProofEnvelope struct
  6. Compute expected digest
  7. Recover signer address from signature
  8. Verify signer matches assigned node's authorized worker signer
  9. Validate leaseId matches current job lease
  10. Validate lease not expired, deadline not expired
  11. Rebuild Merkle tree from trace_hashes + output_hash using canonical algorithm (SHA256(0x00||leaf), SHA256(0x01||left||right), odd-node duplication)
  12. Verify merkle_root matches; verify expected fingerprint matches
  13. Validate actual storage bytes against claimed outputHash (output byte validation)
  - Backend rejects obsolete worker signatures (stale-provider separation)
  - If proof is malformed (unparseable envelope, bad encoding): fail attempt, no contract call, follow retry/timeout recovery
  - If proof is structurally valid but cryptographically invalid: persist INVALID verdict, call `submitProof(jobId, leaseId, merkleRoot, outputHash)` on-chain, wait for confirmed `ProofSubmitted`, then call `verifyJob(jobId, false)` to refund
  - If proof is valid: persist VALID verdict, call `submitProof(jobId, leaseId, merkleRoot, outputHash)` on-chain, wait for confirmed `ProofSubmitted`, then call `verifyJob(jobId, true)` to settle
- [x] Blockchain service:
  - Connect to Arbitrum Sepolia via Web3
  - Call contract functions (assignProvider, submitProof, verifyJob, getJob, getPendingWithdrawal)
  - Handle gas estimation + transaction sending
  - Controlled nonce management for idempotent transactions
- [x] Blockchain event listener:
  - Listen to `JobCreated`, `ProviderAssigned`, `ProofSubmitted`, `JobSettled`, `PaymentCredited`, `TimeoutRefundCredited`, `WithdrawalCompleted`
  - Sync events to `blockchain_events` table
  - Update job status based on events
  - Activate `pending_chain` leases on confirmed `ProviderAssigned`
  - Transition `retry_pending` to `assigned` on confirmed reassignment
- [x] Storage service:
  - R2 presigned URL generation (upload + download)
  - File cleanup (24h expiry for inputs, 7d for results)
  - IPFS optional (Pinata API, Post-MVP only)

### Deliverables
- [x] Complete job submission flow (UUID → escrow → queue → assign → execute → prove → verify → pay)
- [x] Idempotent lease management with pending_chain → active lifecycle
- [x] Proof verification working end-to-end with 4-param submitProof
- [x] Blockchain event listener syncing payments and lease confirmations
- [x] DB states distinct from on-chain states

---

## Phase 4: Frontend (Week 5-8)

**Goal:** Complete React UI for providers and users.

**PRD v3.1 sections:** 15 (API Endpoints), user/provider flows

### Week 5-6: Setup + Core Components
- [ ] Initialize Vite + React + TypeScript project
- [ ] Install dependencies:
  - `wagmi`, `viem`, `@rainbow-me/rainbowkit` (wallet connection)
  - `react-router-dom` (routing)
  - `tailwindcss` (styling)
  - `axios` or `fetch` wrapper (API client)
- [ ] Set up API client (`src/api/client.ts`) with JWT interceptor
- [ ] Set up wallet connection (`WalletConnect.tsx`) with MetaMask
- [ ] Create layout components (`Layout.tsx`, `Navbar.tsx`)
- [ ] Set up routing:
  - `/` — Home
  - `/provider/dashboard` — Provider dashboard
  - `/provider/register` — Register node
  - `/user/dashboard` — User dashboard
  - `/user/submit` — Submit job
  - `/user/jobs/:id` — Job detail

### Week 6-7: Provider Dashboard
- [ ] Provider dashboard page:
  - List registered nodes with status (online/offline)
  - Show active jobs, total earnings, uptime
  - "Register GPU Node" button → form (GPU name, VRAM, location)
  - "Download Worker" button → download ZIP
  - Earnings history
- [ ] Node registration flow:
  - Form → POST /v1/nodes → display API key + node ID
  - Show worker setup instructions

### Week 7-8: User Dashboard
- [ ] User dashboard page:
  - "Submit Job" form:
    - Model selector dropdown (from GET /v1/models)
    - File upload (drag-drop, size validation per model)
    - Cost display
    - "Submit & Pay" button
  - Job list with status (queued, running, complete, failed)
  - Job detail page:
    - Status timeline
    - Result download link
    - Blockchain explorer link
- [ ] Job submission flow (user-funded escrow per PRD v3.1):
  - Upload file → POST /v1/jobs → get job_id + fingerprint + contract data
  - Frontend calls `createJob(chainJobId, fingerprint)` via MetaMask (user pays escrow)
  - Frontend submits tx hash to POST /v1/jobs/{id}/confirm-escrow
  - Backend verifies receipt, updates status to queued
  - Show success + redirect to job detail
  - Poll for status updates every 5-10 seconds (no WebSocket)

### Deliverables
- Complete React frontend with provider + user dashboards
- Wallet connection working
- User-funded escrow flow via MetaMask
- Blockchain explorer links
- Dashboard polling at 5-10 second intervals

---

## Phase 5: Worker (Week 4-7, parallel with backend)

**Goal:** Working GPU worker that executes jobs, generates PoAE proofs with canonical algorithm, uploads results.

**PRD v3.1 sections:** 14 (Worker Architecture), 8 (Fingerprint), 9 (EIP-712), 14.5 (Merkle)

### Week 4-5: Core Worker
- [ ] Set up worker project structure
- [ ] `worker.py` — main entry point:
  - Load env vars
  - Initialize aiohttp session
  - Main loop: poll for jobs → execute → submit proof
- [ ] `config.py` — Pydantic Settings from env vars
- [ ] `core/model_loader.py`:
  - Get presigned URL from backend
  - Download model directly from R2
  - Verify model hash after download
  - Cache locally with 24h TTL

### Week 5-6: Execution + Preprocessing
- [ ] `core/preprocessor.py`:
  - `_preprocess_image()` — PIL + torchvision transforms (for YOLO, ResNet)
  - `_tokenize_text()` — HuggingFace BertTokenizer (for BERT)
  - `_preprocess_audio()` — numpy + librosa placeholder (for Whisper)
- [ ] `core/executor.py`:
  - Load model, preprocess input, run inference
  - Return result + timing
- [ ] `core/tracer.py`:
  - Fixed named checkpoints per model adapter (PRD v3.1 Section 14.4)
  - Record SHA-256 hash at each checkpoint
  - No dynamic `model.children()` traversal

### Week 6-7: PoAE Proof + Upload
- [ ] `proof/fingerprint.py`:
  - Deterministic fingerprint using domain separator `NEBULA_POAE_V1`
  - SHA256(domain_separator || protocol_version || model_id || model_hash || preprocessing_version || input_hash)
  - NO pickle, NO datetime, NO runtime-dependent values
- [ ] `proof/merkle.py`:
  - Canonical Merkle algorithm per PRD v3.1 Section 14.5:
    - Leaf hash: SHA256(0x00 || canonicalLeafBytes)
    - Internal hash: SHA256(0x01 || leftChild || rightChild)
    - Odd-node duplication: duplicate final node, hash with itself
  - Preserve checkpoint order; never sort leaves or child pairs
  - NO MerkleTools, NO library defaults
- [ ] `proof/signer.py`:
  - EIP-712 typed-data proof envelope per PRD v3.1 Section 9.1
  - Struct: `ProofEnvelope(protocolVersion, chainId, verifyingContract, jobId, attemptId, leaseId, provider, fingerprint, merkleRoot, outputHash, proofTimestamp, leaseExpiresAt)`
  - Sign with separate worker signing key (NOT provider wallet private key)
  - NO EIP-191 string signing
- [ ] `storage/r2_upload.py`:
  - Get presigned upload URL from backend
  - Upload result bytes to R2
- [ ] `setup.py` — interactive wizard:
  - Prompt for Node ID, API key, Backend URL, worker signing key
  - Write `.env` file
- [ ] Heartbeat loop (every 30 seconds):
  - `POST /v1/worker/heartbeat` with API key
  - Updates DB only; NO contract call; NO lease extension

### Deliverables
- Complete worker that runs on any GPU machine
- Model download, preprocessing, inference, proof generation
- Canonical Merkle algorithm with golden vector tests
- EIP-712 proof envelope with leaseId
- Separate worker signing key
- Result upload to R2

---

## Phase 6: Integration & Testing (Week 8-10)

**Goal:** Everything works end-to-end, tested, secure.

**PRD v3.1 sections:** 20 (Testing Strategy), 21 (Testing and Security Invariants), 22 (Security Threat Model)

### Week 8-9: Integration Testing
- [ ] End-to-end flow test:
  - Frontend → wallet connect → submit job → MetaMask escrow → confirm-escrow → worker picks up → executes → proves → backend verifies → submitProof → verifyJob → payment credited → withdraw
- [ ] Test with real models (YOLOv5, ResNet50)
- [ ] Test with 2+ workers simultaneously
- [ ] Test failure scenarios:
  - Worker crashes mid-job → lease expires → retry_pending → reassignment → eventual timeout refund
  - Invalid proof → verifyJob(false) → refund
  - Network disconnect → idempotent reconciliation
  - Stale lease rejection (LeaseMismatch on-chain)
  - Proof after deadline rejection (JobDeadlineExpired)
  - Proof after reassignment rejection (LeaseMismatch)
- [ ] Backend/worker Merkle convergence testing — verify identical roots from identical inputs
- [ ] DB state vs on-chain state reconciliation testing
- [ ] Idempotent reassignment testing — dropped tx resubmission via receipt/event reconciliation, pending_chain activation, no new lease while previous outcome uncertain
- [ ] Proof verification ordering — malformed proof fails attempt without contract call, cryptographically invalid proof committed and settled false
- [ ] Job price tests — createJob transfers jobPrice, setJobPrice/setMaxJobAmount validation
- [ ] expired_pre_escrow cleanup testing

### Week 9-10: Security + Load Testing
- [ ] Security audit (OWASP top 10):
  - SQL injection tests
  - XSS tests
  - JWT token handling
  - API key security
  - Rate limiting verification
  - Stale-provider signature rejection (backend tests)
  - Stale leaseId rejection (contract tests)
- [ ] Load testing (5+ concurrent jobs):
  - Backend response times
  - Database query performance
  - R2 upload/download speeds
- [ ] Worker reliability test (24hr continuous run)
- [ ] Merkle golden vector tests (10 vectors per PRD v3.1)

### Week 10: Bug Fixes + Polish
- [ ] Fix all integration bugs
- [ ] Add error handling for edge cases
- [ ] Improve UI/UX based on testing
- [ ] Add loading states, error messages, toast notifications
- [ ] Test cross-browser (Chrome, Firefox, Safari)

### Deliverables
- All tests passing
- Security audit complete
- 24hr worker reliability verified
- Merkle golden vectors verified
- All bugs fixed

---

## Phase 7: Deployment & Launch (Week 10-12)

**Goal:** Publicly accessible, monitored, documented.

### Week 10-11: Deployment
- [ ] Deploy smart contract (if not done in Phase 1):
  - `forge create` to Arbitrum Sepolia
  - Verify on Arbiscan
- [ ] Deploy backend to Oracle OCI Always Free:
  - Keep the tenancy on Free Tier; create only resources labelled Always Free eligible
  - Use the reviewed ARM64 Docker Compose definition under `deploy/oci/`
  - Run Alembic before starting the API; keep all secrets in the VM's mode-0600 environment file
  - Terminate HTTPS with Caddy on a free hostname; never expose FastAPI port 8000 publicly
  - Keep the five runner containers disabled for BE-002 and activate them only through their reviewed integration ticket
- [ ] Deploy frontend to Vercel:
  - Connect GitHub repo
  - Auto-deploy on push
  - Configure env vars
- [ ] Setup Supabase:
  - Create project
  - Run migrations (12 tables)
  - Enable backups
- [ ] Setup Cloudflare R2:
  - Create bucket
  - Configure custom domain: `r2.nebula.ai`
  - Upload model files

### Week 11-12: Monitoring + Launch
- [ ] Setup Uptime Robot:
  - Monitor `https://api.nebula.ai/v1/health/live`
  - Monitor `https://nebula-app.vercel.app`
- [ ] Configure logging:
  - Backend and runner logs through Docker Compose on OCI
  - Error tracking
- [ ] Write README.md:
  - Project overview
  - Architecture diagram
  - Setup instructions
  - API documentation
- [ ] Write worker setup guide:
  - Download instructions
  - Step-by-step setup
  - Troubleshooting
- [ ] Beta testing:
  - Invite 10 testers
  - Send worker setup instructions
  - Monitor logs for errors
  - Collect feedback
- [ ] Fix critical bugs from beta
- [ ] Public announcement:
  - Twitter/Discord post
  - Demo video

### Deliverables
- All services deployed and accessible
- Monitoring active
- Documentation complete
- Beta feedback incorporated
- Public launch

### Temporary owner-operated demo-host contingency (non-canonical)

While OCI Always Free capacity is unavailable, an owner may use the temporary
personal-laptop demonstration route documented in
[`OWNER_OPERATED_DEMO_HOST.md`](runbooks/OWNER_OPERATED_DEMO_HOST.md). This is
not a replacement for the OCI deployment target above and does not amend the
PRD or permanent Phase 7 plan. It preserves the same Vercel same-origin
`/api/v1/*` rewrite, private FastAPI port, Caddy TLS termination, Supabase
database, and disabled-runner posture, but it is available only while the
owner-operated laptop, Docker engine, home network, router forwarding, and
DuckDNS updater remain online. The separate
`scripts/be002_owner_operated_demo_wizard.sh` profile is reversible: stop it
before running the unchanged OCI wizard, which will replace the frontend
rewrite only after OCI HTTPS is verified.

---

## Dependency Graph

```
Phase 0 (Scaffolding)
    │
    ├──> Phase 1 (Smart Contract)
    │         │
    │         └──> Phase 3 (Backend Core) ──> Phase 6 (Integration)
    │                    │
    ├──> Phase 2 (Backend Foundation) ──> Phase 3
    │         │
    │         └──> Phase 4 (Frontend) ──> Phase 6
    │
    └──> Phase 5 (Worker, parallel with Phase 2-3) ──> Phase 6
                                                          │
                                                          └──> Phase 7 (Deployment)
```

## Critical Path

```
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 6 → Phase 7
                         └→ Phase 4 ─┘
              └→ Phase 5 ──────────┘
```

**Estimated time on critical path:** 10-11 weeks (with 1-2 weeks buffer)

---

## Weekly Schedule

| Week | Phase | Focus |
|------|-------|-------|
| 1 | Phase 0 + 1 | Scaffolding + Smart contract build |
| 2 | Phase 1 + 2 | Contract deploy + Backend setup |
| 3 | Phase 2 | Auth + Node registration |
| 4 | Phase 2 + 3 + 5 | Security + Job submission + Worker core |
| 5 | Phase 3 + 5 | Scheduler + Worker execution |
| 6 | Phase 3 + 5 | Proof verification + Worker PoAE |
| 7 | Phase 4 + 5 | Frontend escrow flow + Worker upload |
| 8 | Phase 4 + 6 | Frontend polish + Integration testing |
| 9 | Phase 6 | Security + Load testing |
| 10 | Phase 6 + 7 | Bug fixes + Deployment |
| 11 | Phase 7 | Monitoring + Beta |
| 12 | Phase 7 | Launch |

---

## Tech Stack

| Component      |                      Technology                     |
|----------------|-----------------------------------------------------|
| Smart Contract | Solidity 0.8.20 + Foundry + OpenZeppelin v5         |
| Backend        | FastAPI + SQLAlchemy + Alembic                      |
| Database       | PostgreSQL (Supabase free tier)                     |
| Frontend       | React + Vite + TypeScript + Tailwind                |
| Wallet         | wagmi + viem + MetaMask                             |
| Worker         | Python + PyTorch + aiohttp                          |
| Storage        | Cloudflare R2 (private by default)                  |
| Blockchain     | Arbitrum Sepolia Testnet                            |
| Deployment     | Vercel Hobby (FE, personal/non-commercial staging) + OCI Always Free (BE/runners) |
| Monitoring     | Uptime Robot                                        |

**Optional (Post-MVP):**
- IPFS publication via Pinata
- Redis queueing (only if measured justification)
- WebSocket updates (only if polling creates capacity problem)

---

## Traceability Table

| Plan task | PRD v3.1 section | Component | Dependency |     Acceptance test   |
|-----------|------------------|-----------|------------|-----------------------|
| Directory structure | 13.1 | All         |     None   | All directories exist |
| foundry.toml config | 11.1 | Contract | Phase 0 | `forge build` succeeds |
| JobState enum (no Cancelled) | 10.1, 11.1 | Contract | Phase 0 | Enum compiles with 6 values |
| createJob(bytes32, bytes32) | 11.1, 12.2 | Contract | Phase 0 | Creates job, locks USDC |
| assignProvider (initial + reassign) | 10.2, 11.2 | Contract | Phase 0 | Initial and reassignment work |
| submitProof(jobId, leaseId, merkleRoot, outputHash) | 11.2, 11.3 | Contract | Phase 0 | LeaseId validated on-chain |
| verifyJob + pull payments | 12.2, 12.3 | Contract | Phase 0 | Settlement via pendingWithdrawals |
| requestTimeoutRefund | 12.4 | Contract | Phase 0 | Refund after deadline, revert before |
| withdraw (CEI) | 12.3 | Contract | Phase 0 | Balance zeroed before transfer |
| setMaxJobAmount (_max >= jobPrice) | 11.1 | Contract | Phase 0 | Event emitted, reverts if below jobPrice |
| setJobPrice + jobPrice | 11.1, 12.1 | Contract | Phase 0 | Transfers exactly jobPrice, price validation works |
| Contract test suite | 21.1 | Contract | All contract tasks | 46+ tests pass |
| 12-table migration | 16.3 | Backend | Phase 0 | All tables created with constraints |
| Auth endpoints | 15, 16 | Backend | Phase 2 | Challenge/verify/refresh flow |
| Node registration + heartbeat | 15 | Backend | Phase 2 | Heartbeat updates DB only |
| Job creation + confirm-escrow | 13.1, 15 | Backend | Phase 3 | User-funded escrow via MetaMask |
| Scheduler + lease management | 13.3 | Backend | Phase 3 | Idempotent pending_chain lifecycle |
| Proof verifier (12-step) | 9.4, 13.5 | Backend | Phase 3 | Canonical Merkle, EIP-712 validation |
| submitProof 4-param call | 11.3 | Backend | Phase 3 | Contract validates leaseId |
| Blockchain event listener | 13.6 | Backend | Phase 3 | Events sync to DB |
| Reconciliation service | 13.7 | Backend | Phase 3 | DB vs on-chain state comparison |
| Idempotent reassignment (backend) | 13.3 | Backend | Phase 3 | Dropped tx detected via receipt, replacement via controlled nonce |
| Proof verification ordering | 11.3, 13.5 | Backend | Phase 3 | Malformed fails attempt, invalid committed and settled false |
| MetaMask escrow flow | 13.1 | Frontend | Phase 3 | User calls createJob via wallet |
| Dashboard polling | 15 | Frontend | Phase 4 | 5-10s interval, no WebSocket |
| Canonical Merkle algorithm | 14.5 | Worker | Phase 5 | Golden vectors pass |
| Deterministic fingerprint | 8.2 | Worker | Phase 5 | No pickle/datetime |
| EIP-712 proof envelope | 9.1 | Worker | Phase 5 | Includes leaseId |
| Separate signing key | 14.6 | Worker | Phase 5 | Not provider wallet |
| Heartbeat (DB-only) | 14.6 | Worker | Phase 5 | No contract call |
| Integration testing | 20, 21 | All | All phases | End-to-end flow works |
| Security testing | 22 | All | Phase 6 | OWASP top 10 passes |
| Deployment | — | All | Phase 7 | All services accessible |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Smart contract bug | Comprehensive Foundry tests (46+), audit before mainnet |
| Merkle algorithm divergence (backend vs worker) | Canonical algorithm defined in PRD v3.1 Section 14.5; golden vector tests; identical implementation enforced |
| Lease/contract divergence | DB states distinct from on-chain states; reconciliation service compares periodically |
| Provider assignment failure | Idempotent blockchain reconciliation; pending_chain → active lifecycle; no work before confirmation |
| Chain reorganizations | Event listener handles reorgs; reconciliation service detects discrepancies |
| Verifier outage | verifyJob remains callable during pause; users can always requestTimeoutRefund after deadline |
| Worker crashes | Auto-restart, heartbeat detection, lease expiry → retry → eventual timeout refund |
| Stale lease proof acceptance | On-chain leaseId validation in submitProof; LeaseMismatch error; tests for stale/expired/reassigned |
| Network issues | Retry logic with exponential backoff; idempotent transactions with controlled nonce |
| R2 downtime | Model cached locally on worker (24h TTL) |
| Database issues | Supabase backups, UUID-based IDs prevent conflicts |
| Blockchain congestion | Arbitrum Sepolia has fast confirmations (~250ms) |
| Scope creep | Strict adherence to PRD v3.1, MVP-only features |
| Honest PoAE limitation | Workers can fabricate internally consistent hashes; centralized verifier can authorize incorrect verdicts; documented in PRD v3.1 Section 24 |
| Redis not needed | Optional Post-MVP; not a deployment blocker |
| IPFS not needed | Optional stretch; not a deployment blocker |



HTTP API → PostgreSQL → scheduler/dispatcher → contract interaction
→ worker proof submission → proof verification → settlement
→ event reconciliation → final API result