# Nebula AI Cloud Post-Phase-3 Execution Roadmap

Status: approved planning handoff; implementation has not started
Prepared: 2026-09-08
Verified starting commit: `7fc457f` (`feat: close Phase 3 end-to-end integration`)
Contract security commit: `ab42722` (`security: harden settlement contract and invariants`)

This document is the continuation point after the Phase 3 Integration Closure.
It is intentionally more specific than the high-level development plan. A new
agent must read this file before changing deployment, frontend, worker, storage,
or integration code.

The immediate objective is:

> Rehearse and deploy the verified contract to Arbitrum Sepolia without
> weakening the existing local flow, then add one thin frontend journey, one
> real ResNet50 worker adapter, and the remaining staging/security gates in
> dependency order.

This is not permission to deploy, spend funds, create external accounts, push
commits, or use secrets. Those actions require the project owner to be present
and explicitly approve the exact action.

The implementation-sized work items for this roadmap are tracked in
`docs/POST_PHASE3_SUB_TICKETS.md`. Agents must use that ticket dependency graph
and may not treat a later ticket as authorized merely because an earlier ticket
is complete.

## 1. Canonical authority and current truth

Read these completely, in this order:

1. `AGENTS.md`
2. `CONTEXT.md`
3. `docs/NEBULA_PRD_v3.1.md`
4. `docs/DEVELOPMENT_PLAN.md`
5. `docs/INTEGRATION_CLOSURE_REPORT.md`
6. `docs/INTEGRATION_CLOSURE_SNAPSHOT.md`
7. This roadmap
8. Current contract, deployment scripts, generated artifacts, migrations,
   backend runners, frontend, worker, and tests relevant to the next slice

The local Phase 3 flow is already established:

```text
HTTP API -> PostgreSQL -> scheduler -> assignment dispatcher
-> real Anvil NebulaVerifiableAI -> protocol worker -> real ProofVerifier
-> submitProof -> verifyJob -> eth_getLogs event poller
-> PostgreSQL projection/reconciliation -> GET /v1/jobs/{id}
```

Do not replace or bypass this flow. In particular, do not replace authentic
receipts/logs with fabricated data, call contract lifecycle functions directly
from tests that are intended to prove a public journey, use
`FakeBlockchainBackend` in authoritative end-to-end tests, manually copy the
ABI, or update database lifecycle state as a shortcut.

Verified baseline at `7fc457f`:

```text
Backend: 321 passed, 0 skipped in each required suite order
E2E:     4 passed twice consecutively
Foundry: 125 passed, 0 failed, 0 skipped
ABI SHA-256:
  57a205796f5ea3e9189e281af31dcdc337386075f1ae8060a0d34fe3c5aaf0e9
Runtime template SHA-256:
  54b4029baa8f1487adda2c3f7a676b54524ec8a591b61f843e63d349aa58faef
Compiler: 0.8.20+commit.a1b79de6, optimizer 200, viaIR=true, EVM shanghai
Alembic head: 0008_proof_verification_claims
```

Strict `mypy app` is not a green baseline. The closure report records 324
pre-existing errors, mainly from legacy SQLAlchemy typing and missing stubs.
Do not hide this or claim strict typing passes. A separate typed-ORM cleanup may
be planned, but it must not be mixed into deployment or frontend work.

## 2. Correct interpretation of project phase status

| Area | Current status | Remaining gate |
|---|---|---|
| Phase 0 scaffolding | Complete enough to continue | Keep configuration and documentation current |
| Phase 1 contract | Implementation/security tests complete locally | Deployment script, Arbitrum Sepolia deployment, explorer verification, staging smoke |
| Phase 2 backend foundation | Complete locally | Hosted PostgreSQL/storage validation is later deployment work |
| Phase 3 backend core | Complete locally | Preserve the Integration Closure gates |
| Frontend | Route/page skeleton only | Browser/backend prerequisites and one real wallet-to-result journey |
| Worker protocol | Connected with `DeterministicFixtureExecutor` | One safe deterministic ResNet50 adapter and real GPU validation |
| Integration testing | Substantially started locally | Browser, real model/GPU, multi-worker, load/security, and public staging coverage |
| Public deployment | Not started | Hosted backend/frontend/database/storage and operational runbooks |

Do not describe Phase 6 as entirely unstarted: the local integration closure is
meaningful Phase 6-style evidence. It is not, however, proof of browser,
real-GPU, hosted-service, or public-testnet readiness.

## 3. Non-negotiable architecture and security invariants

Every future slice must preserve all of the following:

1. The AI user funds escrow from their own wallet. The backend or GPU provider
   must never fund user jobs silently.
2. Job UUIDs are the first 16 bytes of `bytes32`; the lower 16 bytes are zero.
3. The backend establishes the job fingerprint from exact input bytes, the
   approved model identity/version/hash, preprocessing version, and protocol
   version. Browser-provided hashes are not authoritative.
4. `assignProvider`, `submitProof`, and `verifyJob` are verifier-authorized.
5. The backend verifier key and worker signer key are distinct. Neither is the
   GPU provider's payout wallet key.
6. The assigned provider address in the proof and contract determines payout.
7. Lease ID, attempt ID, proof timestamp, lease expiry, job deadline, chain ID,
   and verifying contract remain bound into the proof envelope.
8. Result integrity is SHA-256 over the exact canonical result bytes returned to
   the user, not a parsed or reserialized representation.
9. Merkle leaves are `SHA256(0x00 || leafBytes)`; internal nodes are
   `SHA256(0x01 || left || right)`; odd nodes duplicate; ordering is fixed; no
   sorting and no third-party default algorithm.
10. Proof signing remains full EIP-712. Do not use EIP-191 personal-message
    signing for proof envelopes.
11. Contract settlement and refunds remain mutually exclusive, pull-payment
    based, and replay-safe.
12. Chain writes remain persist-before-broadcast with durable intent, concrete
    chain-instance identity, and PostgreSQL-coordinated signer nonces.
13. Receipt confirmation and event projection use the configured chain,
    contract, real transaction/receipt/logs, canonical ABI, and confirmation
    policy.
14. PostgreSQL transactions and row locks are not held during RPC, storage, or
    model network I/O.
15. A worker receives only active/current leases. Old, expired, reassigned, or
    non-current workers cannot download inputs/models or submit results/proofs.
16. `job.input_hash` is never overwritten by an output hash. Result metadata
    stays in dedicated result fields.
17. Private storage keys are not exposed unnecessarily. Result downloads remain
    freshly authorized through the backend.
18. Secrets, raw signed transactions, API keys, seed phrases, private keys, and
    internal trace contents must not appear in logs, fixtures, screenshots,
    reports, commits, shell history, issue text, or chat.
19. The ABI is generated only from the Foundry artifact through
    `scripts/sync_contract_artifacts.py`; explorer output is not an ABI source.
20. Contract behavior or interface changes require a documented blocking defect,
    a fresh threat model, Solidity security review, Foundry regression suite,
    regenerated artifacts, and explicit owner approval before deployment.

## 4. Required working method for every continuation

### 4.1 Re-entry preflight

Before editing, run:

```bash
git status --short
git diff --check
git diff --stat
git log --oneline --decorate -10
git rev-parse HEAD
```

Expected clean starting point is `7fc457f`. If the tree is dirty, inspect every
change and determine ownership. Never reset, delete, overwrite, stash, amend,
or reformat user work merely to obtain a clean tree.

Then inventory every repository-installed skill as required by `AGENTS.md`.
The repository inventory currently names:

```text
solidity-foundry-security, tdd, domain-modeling, code-review,
diagnosing-bugs, research, codebase-design, grill-with-docs,
improve-codebase-architecture, handoff, ask-matt,
setup-matt-pocock-skills, teach, wizard
```

The active catalog may differ. Read every applicable `SKILL.md` completely and
record discovered/applied/not-applied skills in that slice's report. Solidity
work requires `solidity-foundry-security`; all implementation uses TDD; all
TypeScript/React work must use the mandated Matt Pocock skills when available.
If a mandatory frontend skill is missing from the active catalog, report that
fact before proceeding and install it only with owner authorization.

### 4.2 Slice discipline

Work in this dependency order and keep each slice independently reviewable:

```text
deployment readiness
-> owner provisions identities/funds/RPC
-> owner-authorized Sepolia deployment
-> public-chain smoke through existing backend flow
-> browser/backend prerequisite closure
-> thin frontend vertical slice
-> real ResNet50 worker adapter
-> staging failure/load/security testing
-> hosted services
-> beta and launch polish
```

For every slice:

1. State the exact acceptance gate.
2. Add a failing regression/integration test first where practical.
3. Implement only that slice.
4. Run focused tests.
5. Run affected Phase 1-3 regression suites.
6. Run the authoritative E2E when a public interface, lifecycle, proof,
   contract, storage, or runner changes.
7. Review standards and specification compliance from a fixed base commit.
8. Run secret and generated-artifact staleness checks.
9. Update the relevant report/snapshot.
10. Commit only with explicit authorization; never push or deploy implicitly.

### 4.3 Stop conditions

Stop and ask the owner before continuing if any of these occurs:

- Any private key, seed phrase, RPC credential, API key, or real token is found
  in tracked files or tool output.
- The RPC reports a chain other than `421614` during intended testnet work.
- The official Circle USDC address differs from the configured address.
- The configured USDC address has no runtime code or does not report 6 decimals.
- The contract artifact or generated ABI is stale.
- Deployment would use the backend verifier key as owner, user, provider, or
  worker signer unintentionally.
- Contract code/interface changes appear necessary.
- A migration would target anything other than an explicitly named disposable
  local/staging database.
- Existing tests fail before the new slice begins.
- A command will broadcast, transfer tokens, verify publicly, mutate a hosted
  resource, create a cloud expense, or expose a secret and the owner has not
  explicitly approved that exact action.
- A mainnet chain, real-value token, production database, or production domain
  appears anywhere in the intended target.

## 5. Stage 1 — Deployment-readiness implementation, no broadcast

This is the next implementation slice. An agent can complete it while the owner
is away because it must remain entirely local and must not use real secrets.

### 5.1 Deliverables

Create and test:

- `contracts/script/Deploy.s.sol`
- `contracts/script/Smoke.s.sol` or an equivalently named bounded smoke script
- `contracts/test/Deploy.t.sol`
- A sanitized public deployment manifest schema, for example
  `contracts/deployments/arbitrum-sepolia.json`
- A deployment validation/check script under `scripts/`
- `docs/runbooks/ARBITRUM_SEPOLIA_DEPLOYMENT.md`
- A repeatable human setup wizard under `scripts/` only after its stages and
  destinations have been reviewed with the owner
- `.gitignore` coverage for `contracts/broadcast/` and all local deployment
  environment files before running any broadcast rehearsal

Never commit Foundry broadcast journals without inspecting them. They may
contain signed transaction material and are not the canonical deployment
manifest.

### 5.2 Deployment script behavior

The contract constructor accepts only the USDC address and initially makes
`msg.sender` both owner and verifier. The script must therefore apply privileged
configuration in this order:

```text
validate configuration
-> deploy NebulaVerifiableAI(USDC)
-> setVerifier(BACKEND_EXECUTOR_ADDRESS)
-> optionally setMaxJobAmount/setJobPrice if explicitly configured
-> transferOwnership(CONTRACT_OWNER_ADDRESS) last, if owner differs from deployer
-> read every value back and assert it
```

Required validation before `vm.startBroadcast`:

- Network mode is explicit: local rehearsal or Arbitrum Sepolia.
- Sepolia mode requires `block.chainid == 421614`.
- USDC, owner, and verifier addresses are nonzero.
- USDC has nonempty runtime code.
- `IERC20Metadata(USDC).decimals() == 6`.
- The verifier is the backend executor address.
- The worker signer and provider payout identities are not accepted as verifier
  configuration inputs.
- Configured `jobPrice` is positive and does not exceed `maxJobAmount`.
- `setVerifier` and all other owner calls occur before ownership transfer.
- The script does not print or serialize private keys.

Required post-deployment assertions:

```text
contract.token() == configured USDC
contract.verifier() == configured backend executor
contract.owner() == configured owner
contract.jobPrice() == intended price
contract.maxJobAmount() == intended maximum
contract.paused() == false
contract.totalEscrowed() == 0
contract.totalPendingWithdrawals() == 0
contract.invariant_solvency() == true
```

Do not assert that the raw on-chain runtime bytecode hash must exactly equal the
artifact's runtime-template hash without resolving immutable references. The
USDC address is Solidity `immutable` and is embedded into deployed runtime
bytecode. Record both the artifact template hash and actual on-chain code hash,
then rely on deterministic compiler settings, explorer source verification,
immutable-reference-aware comparison, and getter assertions.

### 5.3 Public deployment manifest

The sanitized manifest must contain public facts only:

```json
{
  "network": "arbitrum-sepolia",
  "chain_id": 421614,
  "contract_address": "0x...",
  "usdc_address": "0x75fa...AA4d",
  "owner_address": "0x...",
  "verifier_address": "0x...",
  "deployment_transaction_hash": "0x...",
  "deployment_block": 0,
  "deployed_at_utc": "...",
  "source_commit": "...",
  "abi_sha256": "...",
  "runtime_template_sha256": "...",
  "on_chain_code_sha256": "...",
  "compiler": "0.8.20+commit.a1b79de6",
  "optimizer_enabled": true,
  "optimizer_runs": 200,
  "via_ir": true,
  "evm_version": "shanghai",
  "explorer_url": "https://sepolia.arbiscan.io/address/0x...",
  "source_verified": true
}
```

Before an actual deployment, placeholder values or a separate schema fixture
must be used. Never commit a manifest claiming deployment before the receipt,
block, getters, code, and explorer verification are confirmed.

### 5.4 Local rehearsal

The deployment and smoke scripts must first run against fresh Anvil with a fresh
MockUSDC. The rehearsal must use distinct deterministic test accounts for:

- deployer/owner
- verifier/backend executor
- AI user
- GPU provider payout wallet
- worker signer

The rehearsal must prove:

```text
deploy -> configure verifier/owner -> approve -> createJob
-> assignProvider -> submitProof -> verifyJob(true)
-> provider pending withdrawal -> provider withdraw
```

It must also assert unauthorized assignment/settlement fails, invalid settlement
credits the user, duplicate settlement fails, pause behavior remains correct,
and contract solvency holds. Reuse existing helpers rather than creating a
second ABI or a second UUID/Merkle/EIP-712 implementation.

### 5.5 Stage 1 verification gate

```bash
cd contracts
forge fmt --check
forge build
forge test
forge test --gas-report
forge snapshot --check

cd ..
python scripts/sync_contract_artifacts.py --check

cd backend
source .venv/bin/activate
python -m pytest -q
uv run ruff check .
uv run ruff format --check .
```

The PostgreSQL-gated backend run must point only to the local `nebula_test`
database and must report zero skips. Run the deployment rehearsal twice against
fresh Anvil processes. No real RPC broadcast is allowed in this stage.

## 6. Stage 2 — Owner-only identity, RPC, faucet, and explorer setup

These tasks require the owner because agents cannot safely custody wallet
secrets, accept faucet terms, solve CAPTCHA, approve wallet prompts, create paid
accounts, or authorize broadcasts.

### 6.1 Required identity separation

Use distinct identities whenever practical:

| Identity | Purpose | Needs testnet ETH | Needs testnet USDC | Secret location |
|---|---|---:|---:|---|
| Deployer | Broadcast contract creation/configuration | Yes | No | Owner-controlled local wallet/keystore only |
| Contract owner | Pause and configuration authority | Yes for admin calls | No | Hardware wallet or owner-controlled wallet; never backend env |
| Backend verifier/executor | Assign, submit proof, settle | Yes | No | Backend secret store/local ignored env |
| AI user | Approve/create job and withdraw refunds | Yes | Yes | Browser wallet only |
| GPU provider | Receive and withdraw credited payment | Yes for withdrawal | No | Provider browser wallet only |
| Worker signer | Sign EIP-712 proof envelopes | No | No | GPU node secret store/local ignored worker env |

For a testnet-only rehearsal, deployer and owner may be the same wallet if this
is explicitly recorded. The backend verifier, AI user, GPU provider, and worker
signer must remain conceptually and cryptographically distinct.

Never paste a seed phrase or private key into chat. Never pass private keys as
literal command-line arguments, because they can enter shell history or process
lists. Prefer an encrypted Foundry keystore or an ignored, permission-restricted
environment file. Check it with:

```bash
chmod 600 <local-secret-env-file>
git check-ignore -v <local-secret-env-file>
```

If `git check-ignore` does not show an ignore rule, stop before writing secrets.

### 6.2 Verify current public network facts

At execution time, verify again from primary sources:

- Arbitrum chain information:
  <https://docs.arbitrum.io/for-devs/dev-tools-and-resources/chain-info>
- Circle USDC contract addresses:
  <https://developers.circle.com/stablecoins/usdc-contract-addresses>
- Circle testnet faucet: <https://faucet.circle.com/>
- Arbitrum Sepolia explorer: <https://sepolia.arbiscan.io/>

Values verified when this roadmap was written:

```text
Chain: Arbitrum Sepolia
Chain ID: 421614
Public HTTP RPC: https://sepolia-rollup.arbitrum.io/rpc
Explorer: https://sepolia.arbiscan.io/
Circle testnet USDC: 0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d
```

Arbitrum's official chain page states that its public RPC endpoints do not
provide WebSocket support. The current example
`ARBITRUM_SEPOLIA_WS=wss://sepolia-rollup.arbitrum.io/ws` must not be assumed to
be a working Ethereum JSON-RPC WebSocket. The existing runtime uses bounded HTTP
`eth_getLogs` polling and does not require WebSocket. Remove or clearly mark the
example value unless the owner supplies a verified provider WebSocket URL.

### 6.3 Human faucet procedure

1. Open the official Arbitrum documentation/bridge or a currently recommended
   official faucet route from the chain page.
2. Connect only the intended testnet wallet.
3. Confirm the wallet network says Arbitrum Sepolia and chain ID `421614`.
4. Obtain enough testnet ETH for the deployer, backend verifier, AI user, and
   provider withdrawal wallet. These are separate gas-paying roles.
5. Open Circle's faucet, choose Arbitrum/ARB testnet and USDC, paste the AI user
   address, complete any human verification, and request tokens.
6. Verify receipts and balances on Arbiscan. Do not rely only on wallet UI.
7. Confirm the USDC token contract shown by Circle is exactly the configured
   address before proceeding.

Agents may check public balances and bytecode after the owner supplies public
addresses. Agents must not request, store, or use the owner's wallet secrets.

### 6.4 RPC and explorer setup

The public HTTP RPC is acceptable for an initial smoke test but may rate-limit
event backfills. If the owner creates an Alchemy/Infura/QuickNode-equivalent
endpoint, the endpoint credential is secret even if embedded in a URL.

The owner must:

1. Create/select a project restricted to Arbitrum Sepolia.
2. Copy the HTTPS RPC URL into an ignored local environment or hosted secret.
3. Optionally create a WebSocket endpoint only if the provider documents normal
   Ethereum JSON-RPC subscription support.
4. Create an Arbiscan API key if automated source verification requires it.
5. Store the explorer key only in an ignored environment/secret store.
6. Apply provider-side allowlists, quotas, and spend limits where offered.

The later setup wizard should capture secret values using hidden input, write
them only to explicitly ignored files/secret stores, and ask for confirmation
immediately before any irreversible broadcast. It must never echo secrets.

## 7. Stage 3 — Owner-authorized Arbitrum Sepolia deployment

Do not execute this stage while the owner is unavailable.

### 7.1 Pre-broadcast gate

The agent prepares a deployment summary containing:

- exact source commit and clean `git status`
- exact chain ID returned by the RPC
- deployer, intended owner, verifier, and USDC public addresses
- deployer/verifier ETH balances and AI-user USDC balance
- predicted deployment/configuration transactions
- gas estimate and a testnet-only cost estimate
- contract artifact and ABI hashes
- successful local rehearsal evidence
- whether ownership transfer will occur

The owner must explicitly confirm those public facts and authorize broadcast.

### 7.2 Broadcast pattern

Use the reviewed Foundry script, not a separate ad hoc `forge create`. A typical
shape is:

```bash
cd contracts
forge script script/Deploy.s.sol:Deploy \
  --rpc-url "$ARBITRUM_SEPOLIA_RPC" \
  --chain-id 421614 \
  --broadcast \
  --verify \
  --etherscan-api-key "$ARBISCAN_API_KEY" \
  -vvvv
```

The exact flags must be validated against the installed Foundry version first.
Secrets should be read inside the reviewed script from an ignored environment
or encrypted keystore; do not paste a private key into the command.

If automated verification fails but deployment succeeds, do not redeploy. Save
the transaction/address, diagnose verification, and verify the existing
deployment with the exact compiler/settings/constructor arguments.

### 7.3 Immediate post-broadcast checks

Record the deployment transaction receipt and exact block number. Then check:

```bash
cast chain-id --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast code "$NEBULA_PAYMENT_CONTRACT" --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" "token()(address)" --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" "owner()(address)" --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" "verifier()(address)" --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" "jobPrice()(uint256)" --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" "maxJobAmount()(uint256)" --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" "paused()(bool)" --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" "invariant_solvency()(bool)" --rpc-url "$ARBITRUM_SEPOLIA_RPC"
```

Update public configuration only after all getters match. Set
`CONTRACT_DEPLOYMENT_BLOCK` to the receipt block, not `0`, otherwise the event
poller may scan unrelated history and hit provider limits.

Update the sanitized manifest, `.env.example` placeholders/comments where
appropriate, and the deployment runbook. Real secrets remain untracked.

## 8. Stage 4 — Public-chain smoke through the connected runtime

The contract is not considered usable merely because deployment and direct
calls succeed. Prove the existing connected runtime against Sepolia.

### 8.1 Isolated staging configuration

Use a dedicated disposable database such as `nebula_sepolia`, never
`nebula_test` and never a production database. Apply Alembic through head
`0008_proof_verification_claims`. Use a dedicated local storage directory.

Required backend settings include:

```text
DATABASE_URL=<dedicated staging database>
ARBITRUM_SEPOLIA_RPC=<verified HTTPS RPC>
USDC_SEPOLIA_ADDRESS=<official Circle address>
NEBULA_PAYMENT_CONTRACT=<deployed address>
BACKEND_EXECUTOR_ADDRESS=<verifier address>
BACKEND_PRIVATE_KEY=<verifier secret, ignored>
CHAIN_ID=421614
CONTRACT_DEPLOYMENT_BLOCK=<exact receipt block>
CONTRACT_OWNER_ADDRESS=<owner address>
CONTRACT_VERIFIER_ADDRESS=<same public verifier address>
CONFIRMATION_DEPTH=<explicit staging policy>
FINALITY_DEPTH=<explicit staging policy>
EVENT_BLOCK_RANGE=<provider-safe bounded range>
EVENT_OVERLAP_BLOCKS=2
RUNNER_POLL_INTERVAL_SECONDS=2
RUNNER_BATCH_SIZE=25
RPC_TIMEOUT_SECONDS=10
LOCAL_STORAGE_PATH=<dedicated staging directory>
```

Verify `BACKEND_EXECUTOR_ADDRESS` equals the address derived from
`BACKEND_PRIVATE_KEY` without logging either secret. Verify the contract's
`verifier()` getter equals that address before starting runners.

### 8.2 Process topology

Start independently and capture secret-free structured logs:

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m app.runners receipts
python -m app.runners assignment
python -m app.runners settlement
python -m app.runners events
python -m app.runners reconciliation
```

Each runner is independently stoppable. Do not collapse them into one
monolithic loop to simplify deployment. A process manager may supervise them
later, but each command/interface remains separately testable.

For the first public-chain smoke, use the already-proven deterministic fixture
worker. This isolates chain/RPC/deployment behavior from real-GPU behavior.
Configure the worker with chain ID `421614`, the exact deployed verifying
contract, a node-specific signer, its node API key, and the local backend URL.

### 8.3 Required smoke journey

Use the public interfaces in this order:

```text
AI user authenticates
-> exact input/model bytes are registered in staging storage
-> POST /v1/jobs creates pending_blockchain job
-> wallet approves exact current contract.jobPrice() USDC
-> wallet calls createJob(chainJobId, fingerprint)
-> POST /v1/jobs/{id}/confirm-escrow sends only tx_hash
-> receipt runner/scheduler/assignment runner activate lease
-> worker heartbeat/poll/ack/download/execute/upload/complete
-> real backend ProofVerifier executes all checks
-> settlement runner submits proof and verdict
-> event runner projects confirmed/finalized logs
-> GET /v1/jobs/{id} agrees with contract
-> provider pending withdrawal equals captured job amount
-> provider wallet calls withdraw
-> reconciliation remains clean
```

Record all public transaction hashes, blocks, states, and durations. Do not
record secrets or raw signed transactions. Run the valid journey twice with
different job UUIDs to prove nonce/cursor/idempotency behavior.

Do not wait 24 hours merely to reproduce timeout recovery on testnet. The full
timeout/pause/race matrix remains authoritative locally unless a deliberately
short-deadline test contract is separately designed and approved. Do not change
the production contract constants only to make a smoke test faster.

## 9. Stage 5 — Browser/backend prerequisite closure

Complete these backend interfaces before wiring polished frontend pages. The
current frontend skeleton cannot safely implement the intended flow without
them.

### 9.1 Authoritative user input upload

Current `POST /v1/jobs` accepts client-supplied `input_file_key` and
`input_hash`. That is insufficient for a live browser because the backend must
establish the fingerprint from exact bytes it controls.

Design one small public interface that:

- authenticates the AI user
- accepts a bounded streamed upload, not an unbounded in-memory body
- validates model-specific size, MIME type, extension, and basic file magic
- allocates the job UUID and private storage key server-side
- hashes the exact bytes with SHA-256 server-side
- stores immutably through the storage interface
- computes the fingerprint from the approved model row and server-derived hash
- persists job plus storage metadata transactionally/recoverably
- cleans up abandoned uploads without deleting data referenced by a job
- never trusts browser-provided price, fingerprint, hash, or storage key
- returns the existing safe job response needed for wallet `createJob`

A multipart `POST /v1/jobs` is the preferred deep interface if it can replace
the shallow client-authoritative fields without breaking compatibility. If a
two-step upload is required for R2, use an opaque server-issued upload ID and a
server-side finalize/hash check; do not let the browser choose an arbitrary
private key and claim its hash.

Add tests for empty/oversized/wrong-type input, hash mismatch, duplicate
finalization, abandoned cleanup, unauthorized access, storage failure, and the
existing golden journey.

### 9.2 Browser authentication and refresh decision

Current auth uses an EIP-191 personal signature for login challenges, which is
separate from and must not be confused with EIP-712 proof signing. Preserve the
exact server challenge string when calling the wallet.

Resolve the browser origin/cookie interface before implementing the client:

- The current refresh cookie path is `/api/v1/auth/refresh`, while the backend
  router is `/v1/auth/refresh` unless a frontend reverse proxy deliberately
  exposes `/api/v1`.
- `Secure; SameSite=Strict` works only under an intentional same-site topology.
- Direct Vercel-to-OCI cross-site refresh requires a different cookie/CSRF
  design and `credentials: include`; it must not be improvised.

Preferred approach: expose the backend through a same-origin frontend rewrite,
for example browser `/api/v1/*` -> backend `/v1/*`, keep refresh tokens in
`HttpOnly; Secure` cookies, keep access tokens in memory, and align cookie path,
CORS, logout, refresh rotation, and CSRF/origin checks. Record the final choice
as an ADR because it is security-sensitive and costly to reverse.

Tests must cover challenge reuse/expiry, wallet mismatch, access expiry,
refresh rotation, refresh-token reuse revocation, logout, cookie attributes,
path behavior, allowed/disallowed Origin, and cross-site request behavior.

### 9.3 Provider-facing backend gaps

The current `/v1/earnings` route returns an empty placeholder. Before presenting
a provider dashboard as functional, implement and test:

- authenticated provider-scoped nodes, not merely the public node list
- provider earnings and withdrawal-credit history derived from projected
  payments/events
- current pending-withdrawal amount read safely from the configured contract
- node credential display-once semantics
- node API-key rotation/revocation
- worker-signer registration/rotation with stale signer rejection
- authorization rules for provider-only operations

Do not make provider UI claims that the backend cannot support yet.

### 9.4 OpenAPI and error contract

Generate or validate frontend types from the FastAPI OpenAPI document. Do not
maintain handwritten request/response types that silently diverge. Standardize
safe problem responses for validation, unauthorized, wrong chain, rejected
receipt, stale lease, pending confirmation, RPC unavailable, and storage
failure. Raw traces and signer/storage details never enter browser responses.

## 10. Stage 6 — Thin frontend vertical slice

Build one complete AI-user path before implementing every dashboard card.

### 10.1 Required frontend configuration

Only public values may use `VITE_*`:

```text
VITE_API_BASE_URL
VITE_CHAIN_ID=421614
VITE_CONTRACT_ADDRESS=<public deployed address>
VITE_USDC_ADDRESS=<public official test token address>
VITE_BLOCK_EXPLORER_URL=https://sepolia.arbiscan.io
VITE_WALLETCONNECT_PROJECT_ID=<public client identifier if required>
```

No private key, backend API key, JWT secret, R2 secret, or privileged RPC secret
may enter frontend source, Vite environment, bundle, or browser storage.

Extend the canonical artifact generator to emit the frontend contract artifact
or import a generated artifact from one canonical location. Do not manually
copy the Solidity ABI into TypeScript.

### 10.2 Implementation order

1. Configure `wagmi`/`viem` for Arbitrum Sepolia and explicit wrong-network
   handling.
2. Implement wallet connection and account/chain-change invalidation.
3. Request `/v1/auth/challenge`, sign the exact challenge with the connected
   wallet, verify it, retain the access token in memory, and use the chosen
   refresh-cookie topology.
4. Build a typed HTTP module with authorization, one refresh-and-retry path,
   cancellation, safe errors, and no token logging.
5. Fetch models from the backend; do not rely on the hardcoded model list as
   authoritative pricing or availability.
6. Upload one ResNet50-compatible input through the new authoritative upload
   interface.
7. Read `jobPrice()` and token allowance from the configured contract.
8. If needed, request wallet approval for the exact intended amount; show
   account, chain, token, spender, and amount before signing.
9. Call `createJob(chainJobId, fingerprint)` from the AI user's wallet.
10. Wait for a successful receipt and send only its hash to
    `/v1/jobs/{id}/confirm-escrow`.
11. Poll `GET /v1/jobs/{id}` every 5-10 seconds with backoff, visibility-aware
    pausing, and cancellation on unmount/account change.
12. Render DB workflow state, on-chain state, transaction links, attempt/lease,
    proof status, reconciliation health, refund/payment state, and timestamps.
13. Download results only through the freshly authorized backend endpoint and
    verify content handling; never expose internal storage keys.

Handle wallet rejection, insufficient ETH, insufficient USDC, allowance
failure, replaced/dropped/reverted transaction, delayed confirmations, wrong
chain, expired JWT, RPC outage, backend restart, refund, and user navigation
without duplicating jobs or transactions.

### 10.3 Frontend testing gate

Add Vitest/React Testing Library and browser-level testing appropriate to the
chosen stack. Cover state modules and wallet/backend seams with deterministic
adapters, then keep at least one real browser + Anvil journey.

Required commands must include:

```bash
cd frontend
npm ci
npm run lint
npm run build
npm test
```

Add a test script if none exists. Pin dependency changes through the lockfile;
do not perform a broad framework upgrade in the same slice as wallet wiring.

The thin-slice gate is passed only when a new AI user can connect, authenticate,
upload, escrow, observe execution/settlement, and download a result through the
browser without database manipulation or direct privileged contract calls.

## 11. Stage 7 — One real ResNet50 worker adapter

Keep the existing worker network/proof interface stable:

```python
execute(model_bytes, input_bytes, model_id) -> (canonical_output_bytes, ordered_trace_hashes)
```

Replace the executor adapter, not the polling, lease, upload, Merkle, EIP-712,
or completion protocol. Keep `DeterministicFixtureExecutor` for fast protocol
tests; add a `ResNet50Executor` selected explicitly by configuration/registry.

### 11.1 Safe model artifact format

Do not load arbitrary pickle, arbitrary Python modules, or remote code. Prefer
an approved `safetensors` state dictionary loaded into a code-defined,
version-pinned torchvision ResNet50 architecture. Verify SHA-256 before parsing.
Never enable Hugging Face `trust_remote_code`.

The model registry must record real values for:

- model ID and semantic version
- immutable artifact key/URL
- SHA-256
- framework and exact dependency versions
- preprocessing version
- input type and size limit
- VRAM requirement
- fixed checkpoint names and serialization version

Remove `merkletools` from worker dependencies: the protocol prohibits library
defaults and already has its own canonical implementation. Do not add BERT,
YOLO, Whisper, librosa, or unrelated adapters in the ResNet slice.

### 11.2 Deterministic preprocessing and inference

Specify and test every byte-affecting decision:

- accepted image formats and maximum decoded dimensions
- EXIF orientation policy
- RGB conversion
- resize/crop geometry
- interpolation and antialias behavior
- tensor layout, dtype, range, normalization mean/std
- batch dimension
- device transfer
- `model.eval()` and `torch.no_grad()`/inference mode
- fixed seeds where relevant
- deterministic-algorithm settings
- cuDNN benchmarking disabled
- TF32 policy
- exact top-k tie-breaking
- canonical output JSON field order, separators, number/string formatting, and
  required trailing newline

GPU floating-point kernels can differ by hardware/driver. Do not claim universal
bit-for-bit determinism without evidence. Pin the supported CUDA/PyTorch/
torchvision/driver envelope, define canonical checkpoints carefully, run golden
vectors on CPU and the target GPU class, and document remaining trust limits.

### 11.3 Fixed checkpoints

The existing `worker/core/tracer.py` dynamically walks `model.children()` and
returns fallback strings. That violates the approved fixed-checkpoint model and
must not be used for the real adapter.

ResNet50 must emit exactly the backend-expected ordered names:

```text
preprocess, forward, softmax, topk
```

Define canonical bytes for each checkpoint, hash those bytes with SHA-256, keep
order, append the canonical output hash as the final Merkle leaf, and compare
worker/backend golden vectors. Never log intermediate tensor contents.

### 11.4 Cache and resource safety

The real adapter/model loader must:

- stream download to a temporary file
- enforce configured byte limits and timeouts
- hash before atomic rename into cache
- key cache by artifact hash, not only model ID
- use a file lock for concurrent downloads
- use a 24-hour freshness policy without deleting an in-use artifact
- reject hash mismatch and partial download
- bound decoded image dimensions to prevent decompression bombs
- bound GPU memory and map out-of-memory to safe attempt failure
- clean temporary files on failure
- never hold a database transaction because the worker is a separate process

Rename ambiguous worker `PRIVATE_KEY` to `WORKER_SIGNING_PRIVATE_KEY` with a
deliberate compatibility/deprecation path. The worker signer requires no testnet
funds and must never become the provider payout or backend verifier key.

### 11.5 Worker gate

- Unit tests for exact preprocessing/output/checkpoint bytes.
- At least ten golden model/input vectors.
- Backend/worker fingerprint, Merkle, and EIP-712 convergence.
- Corrupt/truncated/wrong model and input rejection.
- CPU deterministic repeat tests.
- Target NVIDIA GPU repeat tests across process restart.
- Worker crash/retry and stale lease rejection.
- One complete local Anvil real-model settlement.
- One owner-authorized Arbitrum Sepolia real-model settlement.
- No fake verifier success and no direct database state shortcut.

Hardware installation, NVIDIA driver changes, CUDA toolkit changes, and long GPU
reliability runs require the owner's machine/access and explicit approval.

## 12. Stage 8 — Integration, security, and reliability closure

Retain the existing 321-test/125-test baseline and add—not replace—the following:

### 12.1 System journeys

- browser -> wallet -> backend -> Sepolia -> worker -> verifier -> settlement
  -> events -> browser result
- valid ResNet proof/provider credit/withdrawal
- invalid output/refund
- worker death and lease reassignment
- old worker rejected after reassignment
- backend restart with prepared/submitted intents
- RPC disconnect after broadcast
- event poller overlap/backfill/restart
- chain success followed by database failure
- two or more concurrent workers
- five or more concurrent jobs
- duplicate browser submit/confirm/complete
- verifier/refund race
- paused contract matrix
- reconciliation incident behavior

### 12.2 Security review

Perform and document:

- OWASP API/browser threat model
- SQL injection and unsafe filter tests
- reflected/stored/DOM XSS tests
- upload content/size/magic/path traversal/decompression-bomb tests
- JWT expiry, refresh rotation/reuse, logout, CSRF, CORS, and cookie tests
- node API-key hashing, display-once, rotation, revocation, and log-redaction tests
- worker signer rotation and stale signature rejection
- owner/verifier/provider/worker role-separation checks
- RPC response validation and timeout handling
- R2 least-privilege credentials and bucket policy
- dependency and container image scanning
- source/log/test secret scanning
- contract standards/spec review and existing invariant suite

PoAE must be described honestly: it proves commitment consistency, binding,
authorization, and protocol conformance under a trusted backend verifier; it is
not a zero-knowledge proof or trustless proof of correct inference.

### 12.3 Reliability and performance

- 24-hour worker soak test with restart injection
- backend/runners restart testing
- database backup and restore rehearsal
- RPC quota/rate-limit behavior
- bounded event backfill performance
- storage upload/download integrity and latency
- five-plus concurrent job load test with p50/p95/p99 and error rate
- nonce contention and multiple-runner safety
- node capacity correctness under failures
- no open critical/high-severity defects

## 13. Stage 9 — Hosted staging and public MVP

Only begin after the browser and real-worker gates pass locally.

### 13.1 Owner-only external provisioning

The owner must create/approve:

- Supabase project and budget/region
- private Cloudflare R2 bucket and scoped credentials
- OCI Free Tier tenancy, home region, and resources visibly labelled Always
  Free eligible; the account must not be upgraded
- Vercel Hobby project and GitHub connection for personal/non-commercial
  testnet staging
- RPC provider project/limits if public RPC is insufficient
- monitoring/error-tracking accounts
- DNS/custom-domain changes
- CI/CD environments and protected secrets

An agent may draft Terraform/configuration, Dockerfiles, workflows, and a setup
wizard locally. It must not create billable resources, connect accounts, set
external secrets, alter DNS, or deploy without explicit authorization.

### 13.2 Secret placement

| Value | Backend secret | Worker secret | Frontend public env | Repository |
|---|---:|---:|---:|---:|
| Database URL | Yes | No | No | Never |
| JWT secret | Yes | No | No | Never |
| Backend verifier key | Yes | No | No | Never |
| RPC URL containing credential | Yes | Maybe | No | Never |
| R2 access key/secret | Yes | No | No | Never |
| Node API key | No | Yes | No | Never |
| Worker signing key | No | Yes | No | Never |
| Contract/USDC addresses | No | No | Yes | Public manifest/example allowed |
| Chain ID/deployment block | No | No | Yes | Public manifest allowed |

Use least-privilege R2 credentials, separate staging/production databases and
buckets, migration backups, the OCI VM's mode-0600 secret environment file,
Vercel project settings, protected CI environments, and explicit rollback
procedures.

### 13.3 Hosted gate

- Alembic upgrade from empty and current staging schema succeeds.
- Readiness fails when database/RPC/storage/contract configuration is invalid.
- Backend processes include API plus every independent runner.
- Frontend uses the intended same-origin/proxy auth topology.
- R2 objects are private and accessible only through authorized flows.
- Contract address, chain ID, deployment block, ABI, and EIP-712 domain agree in
  frontend, backend, worker, and public manifest.
- Monitoring covers API liveness/readiness, runner progress, event cursor lag,
  failed/replaced transactions, critical reconciliation incidents, storage
  failures, worker heartbeat, and job latency.
- Backup/restore and rollback are demonstrated.
- Ten consecutive public staging jobs complete and reconcile.

## 14. Stage 10 — Beta and launch polish

After the hosted gate:

- Write public README, architecture diagram, deployment/runbook, worker setup,
  troubleshooting, security model, and PoAE limitations.
- Test current Chrome, Firefox, Safari, and mobile layouts.
- Run a small beta with at least five AI users and one external GPU provider.
- Demonstrate valid payout, tamper/refund, worker failure/reassignment, and
  reconciliation.
- Triage feedback by severity; block launch on critical/high defects.
- Do not deploy to mainnet or use real-value assets as part of this roadmap.

## 15. Verification matrix after future changes

### Contract or artifact changes

```bash
cd contracts
forge fmt --check
forge build
forge test
forge test --gas-report
forge snapshot --check

cd ..
python scripts/sync_contract_artifacts.py
python scripts/sync_contract_artifacts.py --check
```

Maintain meaningful contract coverage and all stateful invariants. Do not quote
a misleading numeric production coverage value while the documented Foundry
via-IR source-map limitation remains.

### Backend changes

Use a verified local URL whose database name is exactly `nebula_test`:

```bash
cd backend
source .venv/bin/activate
python -m pytest --collect-only -q
python -m pytest -q
uv run ruff check .
uv run ruff format --check .
alembic heads
```

Required closure-sensitive changes also run default, reverse, Anvil-first, and
PostgreSQL-first orders plus the authoritative E2E twice. Report actual
machine-derived counts and zero required skips.

### Frontend changes

```bash
cd frontend
npm ci
npm run lint
npm run build
npm test
```

Add the test command/framework before claiming frontend completion.

### Worker changes

Run worker unit/golden tests in a clean pinned environment, backend/worker
convergence tests, protocol E2E, CPU determinism, and target-GPU tests. Do not
let an unavailable GPU silently skip a required release gate; record it as a
human/hardware-blocked gate.

### Final hygiene

```bash
git diff --check
git status --short
python scripts/sync_contract_artifacts.py --check
```

Scan changed files for secrets without printing secret values. Review all
generated files and migrations. No commit, push, tag, release, deployment, or
external message occurs without authorization.

## 16. Work allowed while the owner is away

An agent may, without external side effects:

- implement and test Stage 1 deployment/readiness scripts entirely on Anvil
- add deployment manifest schema/tests and runbook
- add safe ignore rules before local broadcast rehearsals
- diagnose/document the browser upload/auth/provider-interface prerequisites
- write tests and local implementations behind existing interfaces
- improve generated ABI/frontend artifact checks
- prepare the human setup wizard but not run it
- run local Foundry/backend/frontend/worker tests
- update this roadmap with evidence

An agent must not while the owner is away:

- use or request a seed phrase/private key
- access browser wallets or approve transactions
- request faucet assets on the owner's behalf
- broadcast to Arbitrum Sepolia
- verify/publish a contract using an owner account
- create/configure billable cloud services
- modify DNS, GitHub/Vercel/OCI/Supabase/Cloudflare settings
- write secrets to files or CI
- deploy backend/frontend/worker
- push, tag, release, or merge without authorization
- change contract behavior/interface
- start later broad feature work before the current gate passes

## 17. Handoff/reporting format

At the end of every slice, update a report with:

1. Starting commit and dirty-tree status
2. Skills discovered, applied, and not applied with reasons
3. Exact scope and files changed
4. Threat model or interface decisions
5. Tests added first and defect each test proves
6. Commands executed and machine-derived results
7. External actions taken, if any
8. Public transaction hashes/addresses/blocks, if any
9. Secret scan result without printing secrets
10. Known limitations and unresolved blockers
11. Files awaiting commit
12. Recommended next single slice

The next agent should begin with **Stage 1 only**. It should not deploy merely
because `Deploy.s.sol` exists. The handoff from Stage 1 to Stage 2 must explicitly
state: local rehearsal is green, exact public values required from the owner,
and no external transaction has been broadcast.

## 18. Skill usage for this roadmap

All repository-documented skills were inventoried through `AGENTS.md`.

Applied:

1. `codebase-design`: preserved the existing blockchain, storage, executor,
   signer, verifier, and runner seams; sequenced work around their interfaces.
2. `domain-modeling`: kept AI user, GPU provider, GPU node, worker signer,
   verifier, lease, proof envelope, verdict, and settlement terminology aligned
   with `CONTEXT.md`; no glossary change was required.
3. `wizard`: mapped every owner-only external step, its produced value, whether
   it is secret, and where it may be stored. The executable wizard is deferred
   until the owner reviews these stages.

Not applied:

- `solidity-foundry-security`: no Solidity implementation was changed in this
  planning slice; it becomes mandatory in Stage 1 review and for any contract
  change.
- `tdd`: no behavior was implemented; every implementation stage above mandates
  test-first work.
- `code-review`: there is no implementation diff to review in this planning
  slice; it is mandatory at every completion gate.
- `diagnosing-bugs`: repository gaps were inspected, but no bug-fix request was
  executed.
- `research`: primary sources were checked directly for time-sensitive network
  facts; its required background-agent workflow was unavailable under the
  active no-delegation constraint.
- Frontend-specific, refactoring, teaching, setup, and session-transition skills
  were not needed to author this roadmap. They must be rediscovered and applied
  when their corresponding implementation stage begins.
