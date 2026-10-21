# Nebula GCP Copy — Continuation Handoff

Prepared: 2026-10-16

## Purpose and status

This document is for an agent working in a separately cloned `Nebula-gcp`
repository while the original `Nebula-AI-OpCode` repository remains the
canonical OCI-oriented checkout. The GCP copy is a reversible, limited
demonstration-host experiment. It must preserve Nebula's protocol, security
model, testnet deployment, and application behavior; only the hosting adapter
may differ.

This is **not** authorization to deploy, incur charges, change cloud accounts,
change DNS, alter the deployed contract, or rewrite the product scope. The
owner must explicitly authorize each external action.

## Start here

Read these in order before modifying the GCP copy:

1. `AGENTS.md` — mandatory skills and engineering rules.
2. `CONTEXT.md` — canonical domain vocabulary.
3. `docs/NEBULA_PRD_v3.1.md` — product/protocol requirements.
4. `docs/POST_PHASE3_SUB_TICKETS.md` — authoritative ticket ledger.
5. `docs/INTEGRATION_CLOSURE_REPORT.md` — local Phase 3 connected-flow proof.
6. `docs/NET002_DEPLOYMENT_REPORT.md` and
   `contracts/deployments/arbitrum-sepolia.json` — deployed contract facts.
7. `docs/NET003_RUNTIME_SMOKE_REPORT.md` — real Sepolia runtime evidence.
8. `docs/BE002_COMPLETION_REPORT.md` and
   `docs/adr/0001-same-origin-browser-auth.md` — browser-auth topology.
9. `docs/WRK001_COMPLETION_REPORT.md` and `docs/WRK002_COMPLETION_REPORT.md`
   — real-model worker completion boundaries.

The older comprehensive handoff,
`docs/NEBULA_AI_CLOUD_HANDOFF_2026-09-26.md`, is useful historical context,
but some of its Git state and test counts predate later commits. Prefer the
ticket ledger and current Git state for status.

## Non-negotiable system facts

### Domain vocabulary

Use the terms from `CONTEXT.md`: **AI user**, **GPU provider**, **GPU node**,
**worker signer**, **job fingerprint**, **proof envelope**, **verifier**, and
**settlement**. Do not collapse the backend verifier, contract verifier, GPU
provider, and worker signer into one identity.

### Deployed contract

- Network: Arbitrum Sepolia, chain ID `421614`.
- Contract: `NebulaVerifiableAI` at
  `0xbD0A2f65ae2C67A313d2883cAed5029A3275a599`.
- The contract is non-upgradeable. Do not redeploy merely to solve a hosting,
  documentation, test, or verification problem.
- Deployment/verification evidence and public configuration belong in the
  manifest and NET-002 report cited above; do not copy private credentials into
  this document or into the new repository.

### Security model that must survive the hosting change

- Backend derives the authoritative job fingerprint from accepted bytes and
  approved model/protocol metadata.
- The contract verifier controls provider assignment; user escrow is settled
  only through the proof/verification lifecycle.
- The backend verifier is trusted PoAE verification infrastructure, not a ZK
  prover. Never describe this system as trustless or as a zero-knowledge proof.
- Browser access tokens stay only in JavaScript module memory. Refresh tokens
  are host-only, `HttpOnly`, `Secure`, `SameSite=Strict`, and scoped to
  `/api/v1/auth`.
- Refresh and logout enforce exact `Origin == FRONTEND_URL`; credentialed CORS
  permits only that origin. Do not weaken this to a wildcard or cross-site
  cookie design for convenience.
- Secrets stay in local ignored files or the cloud secret store. Never commit
  `.env`, `.env.local`, private keys, RPC URLs containing credentials,
  database URLs, DuckDNS tokens, SSH keys, browser tokens, or build artifacts.

## What is completed

| Area | Status | Evidence / boundary |
| --- | --- | --- |
| Phase 0 scaffolding | Done | Repository and documentation baseline exist. |
| Phase 1 contract | Done and deployed | Foundry security suite, deployment, and source verification; see NET-002. |
| Phase 2 backend foundation | Done | FastAPI, async persistence, schema/migrations, authentication and core models. |
| Phase 3 backend core | Done | Scheduling, leases, signing, proof verification, settlement, events and reconciliation; see Integration Closure report. |
| DPL-001 through DPL-005 | Done | Local deployment readiness and manifest/runbook work. |
| HUM-001 through HUM-003 | Done | Owner-controlled testnet prerequisites; do not expose their secret inputs. |
| NET-002 | Done | Arbitrum Sepolia deployment/verification. |
| NET-003 | Done | Two real Sepolia runtime journeys using backend runners and fixture worker. |
| BE-001 | Done | Authoritative bounded input upload. |
| BE-002 | Partial | Local browser-auth implementation is complete; public hosted browser evidence is not. |
| WRK-001 / WRK-002 | Partial | Safe ResNet loader and deterministic CPU executor are complete; production artifact, target GPU and live real-model gates remain. |
| BE-003, frontend tickets, QA/OPS/release | Blocked | Follow the dependencies in the ticket ledger. |

### Verified connected flow

The following was proved locally and then against the deployed Sepolia
contract using a deterministic fixture worker:

```text
HTTP API -> PostgreSQL -> receipt/assignment runners -> contract
-> worker proof submission -> ProofVerifier -> settlement runner
-> event runner -> reconciliation runner -> final API projection
```

NET-003 proves backend/database/contract/fixture-worker integration. It does
**not** prove a public browser journey, a production deployment, or real GPU
inference.

## Current source baseline

The original checkout currently has uncommitted, unrelated documentation work.
Do not assume it belongs in the GCP copy. The last commits relevant to hosting
and this handoff include:

```text
24e9725 fix: improve DuckDNS wizard token input
935a383 deploy: add owner-operated demo host fallback
a21c1f5 deploy: constrain OCI profile to 1 OCPU
9bd6476 deploy: replace Fly with OCI Always Free
0ebd466 feat: implement BE-002 browser auth closure
367d1b3 test: complete NET-003 Sepolia runtime smoke
6f66161 test: close Phase 3 end-to-end integration
```

In a new clone, first record `git status --short`, `git log -1 --oneline`, and
the source commit. Begin from a clean, committed revision. Do not copy ignored
secret files or generated dependency directories from the original checkout.

## Hosting decision for the GCP copy

### Why a GCP adapter is needed

The canonical profile is OCI Always Free: `deploy/oci/` plus
`scripts/be002_production_auth_wizard.sh`. It assumes ARM64, one OCPU, about
six GB RAM, an OCI reserved public IPv4, and OCI SSH. It must remain untouched
in the original repository and is not valid for GCP.

Google Compute Engine's free `e2-micro` allowance is not equivalent to OCI:
it is small, region-limited, and externally assigned VM IPv4 addresses can
incur a charge. Do not call a Compute Engine VM an entirely free deployment
without checking current Google pricing and the owner's account/billing state.

For the zero-cost demonstration objective, investigate **Cloud Run** first:

```text
Vercel browser origin
  -> same-origin /api/v1/* rewrite
  -> Cloud Run FastAPI HTTPS origin
  -> Supabase PostgreSQL + Arbitrum Sepolia

Laptop, only when demonstrating:
  -> deterministic fixture worker and deliberately controlled runner work
```

Cloud Run request-based execution is appropriate only for a lightweight API
demonstration. It is not evidence that the continuous scheduler, dispatcher,
settlement, event, and reconciliation runners can run indefinitely for free.
Do not enable an always-on minimum instance or claim the full runner runtime is
hosted until cost, lifecycle, and acceptance evidence are reviewed.

## GCP copy: allowed changes

Create an isolated hosting adapter rather than a second application:

```text
deploy/gcp-demo/                    # Cloud Run deployment inputs only
scripts/gcp_demo_owner_wizard.sh    # human-only GCP/Vercel steps
docs/runbooks/GCP_DEMO_HOST.md      # operation and OCI switch-back
docs/research/GCP_DEMO_HOSTING.md   # current primary-source research
docs/evidence/GCP_DEMO_*.md         # public, sanitized run evidence only
```

The adapter may add a production Docker image path/configuration only if it is
covered by focused tests and works for both the existing OCI and GCP use cases.
Prefer one runtime interface with provider-specific adapters. Do not create a
GCP-specific FastAPI application, contract ABI, job state machine, auth
protocol, worker protocol, or database schema.

The GCP wizard must:

- perform only owner-controlled steps and never echo secrets;
- use mode-0600 local config or a cloud secret store rather than Git;
- require explicit confirmation before billable, external, or irreversible
  actions;
- keep transaction-signing runners disabled by default;
- accept only a real, deployed HTTPS origin before writing a Vercel rewrite;
- verify public `/ready`, exact frontend origin behavior, and browser auth
  smoke before recording PASS evidence;
- provide a stop/rollback path and an OCI switch-back procedure.

## GCP copy: prohibited changes

Do **not** change any of the following merely because hosting changes:

1. Solidity source, deployed address, ABI semantics, testnet chain ID, USDC
   configuration, owner/verifier role separation, or escrow/settlement rules.
2. Proof envelope, EIP-712/Merkle conventions, authoritative fingerprinting,
   model metadata contract, lease semantics, event reconciliation, or DB
   concurrency safeguards.
3. Browser token ownership, cookie flags/path, exact-origin checks, CORS
   policy, or the Vercel same-origin `/api/v1/*` design.
4. Product scope: no mainnet, real-value assets, paid cloud resources, real-GPU
   completion claim, or release-readiness claim.
5. Existing OCI deployment files in the original repository. The GCP copy may
   remove them only after preserving their history and documenting that it is a
   distinct hosting target.

## Required PRD changes in the GCP copy — only after owner approval

The original PRD correctly names OCI as the canonical target. Therefore do not
silently edit it in the GCP copy just because a branch exists. Once the owner
explicitly decides that the GCP copy is an approved temporary demo target,
make a narrow, traceable amendment to these locations in
`docs/NEBULA_PRD_v3.1.md`:

| PRD area | Required GCP-copy amendment |
| --- | --- |
| Technology table around line 272 | Replace the backend host wording with `Google Cloud Run temporary demo API`; state that continuous runners remain owner-operated/manual for the demo profile. |
| Section 22 deployment architecture | Add a clearly labelled `temporary GCP demo profile` alongside—not disguised as—the OCI canonical profile. State the public Cloud Run HTTPS origin, Vercel rewrite, Supabase, and local controlled worker/runners. |
| Deployment checklist | Replace OCI-specific provisioning steps only for this GCP copy with Cloud Run project/billing guardrails, secret handling, deployment, public health checks, Vercel rewrite, and browser-auth smoke. |
| Architecture/deployment summary references around lines 1891 and 2026 | Replace OCI only where the GCP copy is intended to be self-contained; retain the same application flow and dependencies. |
| Uptime/risk statement around line 1919 | State that this is a demo profile with scale-to-zero/lifecycle constraints, no continuous runner guarantee, free-tier quotas, and no production SLA. |

Do **not** edit protocol requirements, security requirements, role definitions,
acceptance criteria, contract references, testnet deployment facts, or Phase 4+
scope merely to make GCP look more complete than it is.

Any PRD amendment must include a short date, rationale, reversal condition
(`OCI capacity becomes available` or `owner approves a permanent provider
decision`), and a link to the GCP runbook. Do not overwrite historical OCI
rationale; append a temporary deployment-profile decision.

## Safe implementation sequence

1. **Research and decision record.** Use current official Google Cloud
   documentation to confirm Cloud Run region, billing/account requirements,
   free-tier quotas, supported authentication/secret configuration, and
   expected public HTTPS URL. Record what is free, what is merely credit-based,
   and what can charge. Stop if it cannot meet owner constraints.
2. **Threat model.** Extend the deployment configuration threat model for the
   GCP adapter: Vercel rewrite, hostname trust, secret delivery, Cloud Run
   ingress, service account least privilege, unauthenticated health endpoint,
   rate/abuse exposure, and rollback.
3. **Test-first adapter work.** Add focused failing tests for provider-neutral
   image/config invariants before implementation. Do not weaken existing OCI
   tests or modify unrelated application code.
4. **Local verification.** Run formatter/linter/type checks, focused backend
   tests, frontend build/lint/tests, `docker compose config`, and a local
   container readiness test. Preserve historical test results as historical;
   rerun affected checks rather than copying old PASS claims.
5. **Owner wizard.** Create the wizard only after the design is reviewed. It
   must stop before sensitive/irreversible actions and gather secrets locally.
6. **Owner-authorized deploy.** Deploy only after exact project, region,
   account/billing guardrail, service name, and frontend origin are confirmed.
7. **Acceptance evidence.** Verify public HTTPS `/ready`, Vercel same-origin
   rewrite, secure cookie delivery, refresh, logout, and a bounded real E2E
   journey. State exactly which runner/worker processes ran locally versus
   hosted.
8. **Switch-back.** Stop/disable the GCP service, preserve sanitized evidence,
   run the OCI path in the original repository, and update only the Vercel
   rewrite after OCI HTTPS verification.

## Ticket discipline

Do not mark existing tickets complete merely because GCP code exists:

- BE-002 remains `PARTIAL` until public HTTPS, Vercel rewrite, and genuine
  browser auth evidence pass.
- BE-003 and all frontend tickets remain blocked by the ledger dependencies.
- WRK-003 remains blocked until owner hardware/artifact/testnet gates pass.
- QA and OPS/release completion requires their existing acceptance evidence;
  a one-off GCP demo cannot substitute for it.

If the GCP copy needs tracking, add separate `GCP-DEMO-*` tickets with explicit
non-goals instead of changing the status of OCI/production tickets.

## Suggested skills for the next agent

Discover the full skill inventory before each phase and record use in the
applicable completion report. The relevant starting set is:

- `research` — current GCP/Cloud Run pricing, lifecycle, quota, and security
  facts; rely on primary Google documentation.
- `codebase-design` — maintain a single deployment seam with OCI and GCP
  adapters, rather than duplicating the application.
- `domain-modeling` — preserve the system's role and proof terminology; record
  only a real deployment-profile decision.
- `tdd` — any implementation or configuration logic; test before changing.
- `code-review` — fixed-base standards/spec review before a closure claim.
- `wizard` — human-only GCP, Vercel, secret, or deployment steps.
- `diagnosing-bugs` — deployment, build, routing, cookie, or runtime failures.
- `solidity-foundry-security` — mandatory only if Solidity/Foundry changes are
  proposed; hosting work alone must not touch the contract.
- `handoff` — use again at the next session transition.

## Minimum verification commands

Run only the checks relevant to changed paths, then the wider suite required by
the affected ticket. Typical commands are:

```bash
git status --short
git diff --check

cd backend
UV_CACHE_DIR=/tmp/nebula-uv-cache uv run pytest -q

cd ../frontend
npm test
npm run build
npm run lint
```

For deployment configuration, add profile-specific static checks and
`docker compose config` validation. Do not claim a connected GCP result until
the public checks actually run.

## Agent completion checklist

Before handing work back, state:

1. source commit and working-tree status;
2. files changed and why;
3. commands actually run and exact outcomes;
4. whether any public cloud action happened;
5. whether any cost-bearing action was avoided or approved;
6. hosted versus local components during each E2E result;
7. unresolved gates and the next safe ticket.

