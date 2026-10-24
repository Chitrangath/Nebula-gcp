# Nebula Three-Device Production Demo — 36-Hour Execution Plan

**Objective:** deliver one repeatable, production-grade vertical slice: a user without a GPU submits a ResNet50 or BERT job; two independent provider devices compete for assignment; a worker executes and signs the result; the user sees output, proof, escrow, settlement, and provider credit; connected devices are visible.

**Deadline strategy:** protect the critical path. Defer 24-hour soak, broad model support, Whisper, DNS/browser polish, and nonessential QA gates until the vertical slice passes.

## Fixed topology

| Device | Role | Wallet/account |
|---|---|---|
| Device A | User-only browser | AI-user wallet |
| Device B | GPU provider + verifier | Provider wallet; RTX 3050 laptop |
| Device C | Independent GPU provider | Friend’s provider wallet; RTX 5050 |

The contract, backend, R2, and Arbitrum Sepolia deployment already exist. No contract redesign is in scope.

## Ticket order and acceptance gates

### DEMO-001 — Provider identity and node onboarding (4h)

- Finish provider registration UI and API-key rotation UX.
- Show node UUID, wallet, model capability, heartbeat, and online/offline state.
- Register both provider devices with distinct wallets and API keys.

**Done when:** both nodes appear in `GET /v1/nodes`, heartbeat successfully, and can be revoked/rotated without exposing secrets.

### DEMO-002 — Scheduler assignment across two providers (5h)

**Implementation status:** complete and locally verified. Live two-device acceptance remains part of DEMO-008.

- Run two workers concurrently with distinct node IDs.
- Verify leases are exclusive, heartbeats are current, and only one provider receives a given job.
- Add visible assignment state and assigned provider/node to job details.

**Done when:** one submitted job is assigned to exactly one available provider and the other provider remains healthy/available.

### DEMO-003 — Real BERT model path (6h)

**Implementation status:** complete and verified with real ResNet50 and BERT weights on the RTX 3050. Live artifact activation and the RTX 5050 device check remain deployment/DEMO-008 gates.

- Add a real immutable BERT artifact and SHA-256 record.
- Implement BERT model loading/execution behind the existing executor seam.
- Add deterministic preprocessing, output schema, fingerprint, and proof compatibility.
- Keep ResNet50 unchanged and passing.

**Done when:** the same worker protocol completes both `resnet50` image and `bert-base` text jobs with deterministic result/proof metadata.

### DEMO-004 — Production user job experience (5h)

**Implementation status:** complete and browser-contract verified. Production deployment and the Device A live journey remain DEMO-008 acceptance work.

- Replace placeholder/demo-only submission behavior with model discovery from the backend.
- Support image upload for ResNet50 and text upload/input for BERT.
- Show validation, escrow pending/confirmed, queued, assigned, running, proof verified, settled, failed, and refunded states.
- Show result output and safe download only for terminal successful jobs.

**Done when:** Device A can submit either model and follow the job without terminal commands.

### DEMO-005 — Production provider dashboard (4h)

**Implementation status:** complete and browser-contract verified. Production deployment and independent Device B/C acceptance remain DEMO-008 work.

- Replace placeholder provider dashboard and registration page.
- Show provider wallet, node status, active lease, model capabilities, completed jobs, earnings, and settlement links.
- Add clear error/retry states and no secret/API-key rendering after initial creation.

**Done when:** each provider can independently see its node and assigned/completed work from a browser.

### DEMO-006 — Proof, escrow, and payment evidence (3h)

**Implementation status:** complete and browser-contract verified. Public Arbitrum Sepolia reconciliation remains part of the production DEMO-008 run.

- Add explorer links for escrow, assignment, proof, settlement, and refund transactions.
- Show proof fingerprint, verification status, chain ID, block number, and provider credit status.
- Ensure UI values come from authoritative backend/chain responses, not optimistic placeholders.

**Done when:** faculty can independently open Arbitrum Sepolia Explorer and reconcile the displayed job lifecycle.

### DEMO-007 — Connected-device network view (3h)

**Implementation status:** complete and browser-contract verified. Production deployment and the live Device A/B/C state-change demonstration remain part of DEMO-008.

- Add a network page/card showing registered nodes, wallet address, model capability, heartbeat age, status, current lease, and last completed job.
- Display provider/verifier roles without revealing private credentials.
- Add a short explanation of what is on-chain versus backend-observed.

**Done when:** all three devices are visibly represented and their state changes during the demonstration.

### DEMO-008 — Three-device acceptance and demo runbook (6h)

**Implementation status:** acceptance tooling and fresh-operator runbook complete and locally verified. Final closure requires owner-led execution with the independent Device C, two funded browser jobs on the declared provider nodes (same-node sequential execution is valid), and sanitized live evidence.

- Run one ResNet50 job through Device A → scheduler → Device B or C → proof → settlement.
- Run one BERT job after ResNet50; it may be assigned to either compatible provider. Optionally demonstrate assignment recovery to the other provider.
- Stop/restart one provider and verify reassignment or an explicit retry/failure state.
- Capture sanitized job IDs, transaction hashes, screenshots, and recovery commands.

**Done when:** a fresh operator can repeat the two-job demonstration from the runbook without developer intervention.

## Critical-path schedule

1. Hours 0–4: DEMO-001
2. Hours 4–9: DEMO-002
3. Hours 9–15: DEMO-003
4. Hours 15–20: DEMO-004
5. Hours 20–24: DEMO-005
6. Hours 24–27: DEMO-006
7. Hours 27–30: DEMO-007
8. Hours 30–36: DEMO-008 and stabilization

Tickets may be parallelized only after their API contracts are stable. Do not start UI polish before the scheduler and worker path produces authoritative job state.

## Explicitly deferred

- 24-hour soak and long-duration performance gates.
- Whisper/audio support.
- Multiple simultaneous users, autoscaling optimization, and marketplace economics.
- DNS/custom-domain cutover and Vercel routing changes.
- Broad observability dashboards beyond the network/status view.

## Final acceptance script

1. Device A connects as AI user and submits a ResNet50 image.
2. Device B and Device C are online provider nodes.
3. Scheduler assigns the job to exactly one node.
4. Assigned worker executes and submits proof.
5. Backend verifies proof and settles escrow on Arbitrum Sepolia.
6. Device A displays the result, fingerprint, proof status, escrow transaction, settlement transaction, and provider credit.
7. Device A submits a BERT text job; assignment may remain on the same provider or move to the other provider.
8. Network view shows both providers, heartbeat state, capabilities, and completed work.
9. Logs and screenshots contain no private keys, JWTs, API keys, database URLs, or R2 secrets.

## Operational rule

Use the supervised runtime wizard to start and stop laptop workers, but the faculty demonstration itself must be browser-led. Terminal commands are setup/recovery tools, not part of the primary presentation.
