# QA-002 application and protocol security closure

## Result

QA-002 is complete for the reviewed application, protocol, and GCP-demo
surface. No open critical or high-severity finding was identified in the
implemented scope. PoAE is documented as authenticated commitment/protocol
verification performed by a trusted backend verifier; it is not described as
trustless or zero-knowledge.

## Evidence

- Backend security/API/storage/deployment-focused tests: **54 passed**.
- Full backend matrix after the QA-001 fixes: **416 passed**.
- Frontend unit/component tests: **55 passed**.
- Frontend production build: passed TypeScript, OpenAPI-contract, canonical
  contract-artifact, and Vite build checks.
- Foundry contract suite: **152 passed**, including authorization, replay,
  stale-lease, pause, timeout/refund race, reentrancy, solvency, adversarial
  token, and invariant coverage.
- Existing threat models reviewed:
  `docs/security/DEPLOYMENT_CONFIGURATION_THREAT_MODEL.md` and
  `docs/security/GCP_DEMO_DEPLOYMENT_THREAT_MODEL.md`.
- Secret/configuration checks confirm private keys, database credentials, API
  keys, and runner signing material are excluded from the Cloud Run profile,
  logs, generated frontend artifacts, and committed evidence.

## Covered threat classes

- Authentication challenge/verify, refresh rotation and replay-family
  revocation, logout, wrong-origin rejection, CORS preflight, and cookie scope.
- Role separation between AI user, provider, Worker signer, and verifier;
  obsolete signer rejection and API-key-protected Worker endpoints.
- Multipart upload size/type/hash authority, path traversal/object-key
  validation, immutable storage writes, private-object boundaries, and cleanup.
- Idempotency/replay, duplicate escrow/proof/settlement/refund, stale leases,
  authorization failures, pause behavior, and exact timeout boundaries.
- SQL/ORM input binding, error redaction, readiness failure behavior, secret
  placeholder validation, digest-pinned deployment configuration, and runner
  exclusion from Cloud Run.
- Solidity access control, pull-payment/CEI behavior, reentrancy, token return
  anomalies, escrow conservation, and state-machine invariants.
- Frontend memory-only access tokens, same-origin credentials, generated API
  type parity, and absence of unsafe HTML injection sinks in the reviewed UI.

## Scope and residual risk

This is a code/test closure, not a claim of an external penetration test or a
guarantee against unknown dependency vulnerabilities. The public demo remains
subject to Cloud Run/Vercel abuse controls, owner monitoring, dependency update
cadence, and the documented trusted-verifier limitation. QA-003 still covers
long-duration soak, backup/restore, throttling, and measured operational
capacity. No production secrets were printed or changed for this ticket.
