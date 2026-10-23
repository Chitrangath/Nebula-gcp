# Nebula AI Cloud — Current Development Plan

**Baseline date:** 2026-10-22  
**Canonical product specification:** `docs/NEBULA_PRD_v3.1.md`  
**Detailed ticket definitions:** `docs/POST_PHASE3_SUB_TICKETS.md`  
**Purpose:** status-aware execution sequence after local E2E prerequisite and workflow verification

---

## 1. Current baseline

The local E2E environment is operational on Ubuntu/WSL:

- Docker Desktop and Docker Compose are available from WSL.
- Backend, worker, frontend, Foundry, Playwright, PostgreSQL, and CUDA prerequisites pass verification.
- Contract compilation and deployed-artifact consistency checks pass.
- The canonical four-journey local E2E workflow passed twice: **8/8 journeys**.
- `NET-002` and `NET-003` already provide the deployed Arbitrum Sepolia contract and connected-runtime smoke evidence.
- `GCP-004` direct backend acceptance and `GCP-005` Vercel/browser cutover are complete.
- `BE-002` is `DONE`: its public HTTPS, same-origin, real-browser acceptance gate passed on 2026-10-23.

This plan does not replace the PRD or ticket acceptance criteria. It identifies the next executable ticket sequence and the gates between tickets.

## 2. Status vocabulary

| Status | Meaning |
|---|---|
| `DONE` | Required implementation and acceptance evidence exist. |
| `LOCAL DONE` | Local implementation is complete, but an owner-controlled or public-environment gate remains. |
| `READY` | Dependencies are satisfied and work can start. |
| `BLOCKED` | A named dependency or owner-controlled gate must complete first. |
| `PLANNED` | The ticket belongs later in the accepted sequence. |

## 3. Critical path

```text
GCP-004 -> GCP-005 -> close BE-002 -> BE-003
                                      |
                                      v
FE-001 -> FE-002 -> FE-003 -> FE-004 ----+
                                          |
WRK-003 ----------------------------------+-> QA-001 -> QA-002 -> QA-003
                                                            |
                                                            v
                                             OPS-001 -> OPS-002 -> OPS-003 -> REL-001
```

`WRK-003` may proceed alongside the frontend stream after its existing `WRK-002` and `NET-003` prerequisites are reconfirmed. `QA-001` waits for both `FE-004` and `WRK-003`.

## 4. Ordered execution plan

### Step 1 — Establish the hosted backend foundation

**Ticket:** `GCP-004`  
**Status:** `DONE`

Deploy the immutable API image and required GCP foundation, configure durable private storage, and complete direct backend health/storage acceptance.

Acceptance gate:

- Follow `docs/runbooks/GCP004_FOUNDATION_DEPLOY.md`.
- Require explicit owner approval at every cloud mutation or cost-bearing gate.
- Produce the sanitized GCP-004 acceptance evidence required by the runbook.
- Do not change Vercel routing in this ticket.

### Step 2 — Cut over the browser path

**Ticket:** `GCP-005`  
**Status:** `DONE`

Configure the Vercel same-origin `/api/v1/*` route to the deployed backend and perform genuine browser authentication acceptance.

Acceptance gate:

- Follow `docs/runbooks/GCP005_VERCEL_BROWSER_CUTOVER.md`.
- Verify challenge, wallet signature, access-token use, refresh-cookie rotation, replay rejection, logout, and wrong-origin rejection.
- Keep access tokens out of browser storage.
- Validate rollback before considering the cutover accepted.

### Step 3 — Close browser authentication

**Ticket:** `BE-002`  
**Status:** `DONE`

Review the GCP-005 output against `docs/BE002_COMPLETION_REPORT.md`. Mark BE-002 `DONE` only after the public HTTPS and real-browser gate passes.

Acceptance gate:

- The browser uses the deployed frontend origin and same-origin `/api/v1/*` requests.
- Cookie, Origin, CORS, refresh, replay-family revocation, and logout behavior match the auth ADR.
- No secret or bearer token is committed, logged, or persisted in browser storage.

### Step 4 — Complete provider operations and stabilize the API contract

**Ticket:** `BE-003`  
**Status:** `READY`; BE-002 and NET-003 dependencies are complete

Implement the provider-facing backend contract required by the frontend:

- provider-scoped GPU node listing and management;
- earnings and credit history;
- safe pending-withdrawal reporting;
- API-key display-once, rotation, and revocation;
- Worker signer rotation;
- stable OpenAPI schemas and errors for browser client generation.

Acceptance gate:

- Follow the ticket definition in `docs/POST_PHASE3_SUB_TICKETS.md`.
- Use test-first backend development.
- Pass backend unit, integration, authorization, secret-redaction, migration, type, and lint checks.
- Confirm generated browser types cannot silently diverge from FastAPI.

### Step 5 — Build the frontend vertical slice

Execute these tickets strictly in order:

1. **`FE-001` — Frontend harness and generated artifacts**  
   Establish the frontend tests and generate contract ABI/OpenAPI clients. Depends on BE-003 and NET-002.
2. **`FE-002` — Wallet authentication and typed HTTP module**  
   Implement the same-origin browser-auth client. Depends on FE-001.
3. **`FE-003` — AI-user upload and escrow journey**  
   Implement authoritative upload, allowance/approval, and job creation. Depends on FE-002 and BE-001.
4. **`FE-004` — Job lifecycle, reconciliation, and result UX**  
   Implement lifecycle status, reconciliation, and result access. Depends on FE-003 and NET-003.

Acceptance gate:

- Unit and component tests pass for each ticket before advancing.
- A real browser plus Anvil journey passes.
- The owner-authorized Arbitrum Sepolia browser journey passes without direct database manipulation or privileged shortcuts.

### Step 6 — Close the real Worker path

**Ticket:** `WRK-003`  
**Status:** `READY` after reconfirming WRK-002 and NET-003 evidence; may run alongside Step 5

Complete Worker signer migration and real-model system gates using the approved immutable ResNet50 model artifact, deterministic adapter, target GPU, proof envelope, verifier, and Sepolia settlement path.

Acceptance gate:

- The public model artifact hash and metadata are verified.
- Target-GPU deterministic execution passes.
- Signer migration and obsolete-signer rejection pass.
- The real proof-verification and settlement journey completes without mocks.

### Step 7 — Integration, security, and reliability closure

Execute after both FE-004 and WRK-003 are complete:

1. **`QA-001` — Failure, concurrency, and recovery E2E matrix**
2. **`QA-002` — Application and protocol security closure**
3. **`QA-003` — Reliability, performance, backup, and soak gate**

The currently passing local happy-path E2E suite is the baseline, not a substitute for these failure, adversarial, recovery, and soak gates.

### Step 8 — Hosted staging and release

Execute strictly in order:

1. **`OPS-001` — Deployment configuration and provisioning wizard**
2. **`OPS-002` — Owner provisions hosted staging**
3. **`OPS-003` — Deploy and validate hosted staging**
4. **`REL-001` — Beta evidence and launch-readiness decision**

Do not call the project production-ready until REL-001 records an explicit launch decision supported by the preceding evidence.

## 5. Immediate next action

The next action is **BE-003**, implemented test-first against the provider and
browser-contract acceptance criteria in `docs/POST_PHASE3_SUB_TICKETS.md`.
Hosted infrastructure mutations remain owner-controlled and require explicit
approval; BE-003 begins with local backend interfaces and contract tests.

## 6. Working rules for every ticket

1. Read `AGENTS.md`, `CONTEXT.md`, the ticket definition, applicable completion reports, and relevant runbooks before changing code.
2. Inspect all repository-installed skills and apply every skill relevant to the ticket phase.
3. Preserve the deployed contract and artifact hashes unless a separately authorized contract migration requires changing them.
4. Develop test-first and keep changes within one ticket boundary.
5. Run the ticket-specific checks plus affected contract, backend, frontend, Worker, and E2E regression suites.
6. Record commands, results, unresolved external gates, and skill usage in the ticket completion report.
7. Never convert local evidence into a claim about public cloud, browser, blockchain, or target-GPU behavior.

## 7. Plan maintenance

Update this document whenever a ticket crosses a status boundary. Detailed acceptance criteria remain in `docs/POST_PHASE3_SUB_TICKETS.md`; this file should stay focused on current status, sequence, and gates.

## 8. Planning skill record

### Discovered skills

- `solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`, `diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`, `improve-codebase-architecture`, `handoff`, `ask-matt`, `setup-matt-pocock-skills`, `teach`, and `wizard`.

### Applied

1. **`grill-with-docs`**: compared the requested sequence with the PRD, detailed sub-ticket backlog, completion reports, and deployment runbooks before creating a current plan.
2. **`domain-modeling`**: checked ticket descriptions against `CONTEXT.md` and used the canonical terms AI user, GPU provider, GPU node, Worker, model artifact, proof envelope, verifier, verdict, and settlement.

### Not applied

- Implementation, Solidity security, TDD, debugging, code review, research, refactoring, teaching, setup, handoff, and wizard execution skills were not needed because this change only reconciles existing documentation into a current execution sequence. The relevant implementation skills remain mandatory when each ticket begins.
