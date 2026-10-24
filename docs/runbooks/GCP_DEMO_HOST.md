# GCP Demo Host Runbook

Status: GCP-003 closes the local durable-storage and runtime-configuration
contracts. Real bucket/IAM and cross-runtime storage behavior remain unproven
and owner-gated; no cloud, Vercel, DNS, billing, IAM, secret, registry, or
deployment mutation has been performed.

## Purpose and hard boundary

This runbook describes a temporary GCP demonstration profile. Cloud Run may
host only the public FastAPI request path. It does not host continuous Nebula
runners or a GPU node, and it does not change the contract, proof envelope,
lease, verifier, verdict, settlement, database, worker, or browser-auth
interfaces.

OCI remains the original project's canonical long-term target. Nothing in this
GCP copy restores, replaces, or modifies the original OCI deployment files.

## Architecture

```text
Browser
  │ https://<owner-approved-vercel-origin>/api/v1/*
  ▼
Vercel same-origin external rewrite
  │ /api/v1/:path* -> https://<real-cloud-run-origin>/v1/:path*
  ▼
Cloud Run: FastAPI API only

The owner-approved deployment configuration must include the registered GPU
node UUID hosted by the Verifier device as `DEMO_VERIFIER_NODE_ID`. This is a
public runtime identifier, not a wallet address or private signing key.
  ├── request-based CPU, min instances 0, max instances 2
  ├── RUNNERS_ENABLED=false
  ├── Secret Manager references, dedicated runtime identity
  ├── Supabase PostgreSQL + Arbitrum Sepolia RPC over HTTPS
  └── private durable S3-compatible object store
          ▲ shared input/model/result/proof namespace

Owner laptop, started only for a supervised demonstration
  ├── deterministic fixture worker
  ├── receipt runner
  ├── assignment runner
  ├── settlement runner
  ├── event runner
  └── reconciliation runner ── same private object-store contract
```

The browser continues to know only `/api/v1/*` on the Vercel origin. Access
tokens remain in JavaScript module memory. Refresh cookies remain host-only,
`HttpOnly`, `Secure`, `SameSite=Strict`, and scoped to `/api/v1/auth`.
Verify, refresh, and logout continue to require exact
`Origin == FRONTEND_URL`; credentialed CORS continues to allow only that
origin. Direct browser calls to `run.app` remain unsupported.

## Local deployment-readiness artifacts

- `deploy/gcp-demo/cloud-run-service.template.yaml` is JSON-compatible YAML.
  It is inert because all owner-controlled values are unmistakable
  `__...__` placeholders.
- `deploy/gcp-demo/vercel-rewrite.template.json` defines the same-origin route
  and disables API rewrite caching. It is not `frontend/vercel.json` and cannot
  be deployed with its placeholder origin.
- `scripts/validate_gcp_demo_config.py --template` validates the tracked,
  inert contracts. Deployable mode rejects any unresolved placeholder and
  validates HTTPS origins, digest-pinned images, the runtime identity, resource
  limits, secret references, routing order, and cache policy.
- `scripts/gcp_demo_owner_wizard.sh --check` performs local prerequisite and
  template checks. `--plan` prints all thirteen future owner gates. All external
  or mutating execution remains unavailable in GCP-003.
- `docs/security/GCP_DEMO_DEPLOYMENT_THREAT_MODEL.md` records the public
  ingress, identity, secret, abuse/cost, rollback, and OCI switch-back controls.
- `docs/research/GCP002_DEPLOYMENT_READINESS_SOURCES.md` contains the current
  official Google Cloud and Vercel source record.

Use the independent repository explicitly:

```bash
git --git-dir=.git-local --work-tree=. status --short --branch
python3 -m unittest scripts.tests.test_gcp_demo_adapter -v
scripts/gcp_demo_owner_wizard.sh --check
scripts/gcp_demo_owner_wizard.sh --plan
```

These commands do not authenticate, build, upload, deploy, change IAM, create
secrets, change Vercel, or modify DNS.

## Future owner wizard journey

The journey is implemented as three separate owner interfaces:

- `GCP004_FOUNDATION_DEPLOY.md`: foundation through direct backend/storage acceptance;
- `GCP005_VERCEL_BROWSER_CUTOVER.md`: later Vercel and real-browser cutover;
- `GCP006_LAPTOP_DEMO_RUNTIME.md`: supervised laptop Worker and runners.

Each wizard supports non-mutating `--check`, `--plan`, and `--help` modes. Its
interactive mode remains owner-only and was not executed during wizard design.

The owner-approved architecture does not authorize these external actions in
GCP-003. The next ticket must stop at each gate and show the exact proposed
values and commands before the owner confirms them.

| Gate | Owner decision and output | Secret handling |
|---|---|---|
| 1. Project, region, billing | Approve exact project ID, billing account, Tier 1 region, service name, and cost owner | Public identifiers only; write nowhere in GCP-002 |
| 2. Budget and cost review | Approve alert thresholds, recipients, optional eligible spend cap, and availability tradeoff | Billing-account details stay in owner session |
| 3. API enablement | Approve Cloud Run, Artifact Registry, and Secret Manager APIs; add Cloud Build only for a separately selected hosted build | No secret value |
| 4. Private durable storage | Create one private demo bucket; prohibit public domain/r2.dev access | No credentials yet; approve account, bucket, region, and prefix |
| 5. Least-privilege IAM | Approve bootstrap, deployer, optional builder, runtime identity, and bucket-scoped Object Read & Write parent token | Never create/download a GCP service-account key; never broaden the object token beyond the demo bucket |
| 6. Secret creation | Create `DATABASE_URL`, `JWT_SECRET`, R2 credentials, and credential-bearing RPC URL; record only names and numbered versions | Hidden/cloud-console input; never echo, log, or persist in Git; omit Pinata and all signing keys |
| 7. Immutable image review | Review Dockerfile, scan, size, SBOM if available, and immutable digest | No build secrets or credential-bearing arguments |
| 8. Cloud Run deployment | Approve exact service YAML, public invocation, request billing, min 0, max 2, concurrency, timeout, runtime identity, and digest | Secret references only; no runner or signing key |
| 9. Public health | Require direct `/live` `200`, Supabase-backed `/ready` `200`, and unavailable-database `503` behavior | Responses reveal no configuration |
| 10. Cross-runtime storage | Use non-production objects to prove Cloud Run write/laptop read and laptop write/Cloud Run read/delete | Do not record object capabilities or credentials; preserve sanitized hashes only |
| 11. Vercel cutover | Materialize only the observed HTTPS origin in a reviewed preview rewrite; keep `/api/v1/*` and cache opt-out | No credentials in destination URL |
| 12. Browser auth smoke | Verify wallet challenge, refresh rotation, logout, cookie flags/path, exact allowed Origin, and wrong/missing Origin rejection | Tokens never copied to logs/evidence |
| 13. Rollback and OCI switch-back | Record last-good Cloud Run revision, prior Vercel deployment, stop order, evidence, and canonical OCI route | Sanitized identifiers only |

Authorization for this local contract is not authorization for any item above.

The local implementation now selects `FileStorage` only for local/test use and
the S3-compatible durable adapter for the GCP profile. The fail-closed template
contains the complete database, exact frontend origin, JWT lifetime,
Arbitrum Sepolia, contract, and private-storage configuration contract. Local
fake-client evidence is not provider proof: gates 4-6 and 10 must establish the
real bucket, least privilege, endpoint compatibility, and cross-runtime access.

The source paths for the future owner journey are the official
[Cloud Run deploy guide](https://cloud.google.com/run/docs/deploying),
[service identity guide](https://cloud.google.com/run/docs/securing/service-identity),
[Cloud Run secret guide](https://cloud.google.com/run/docs/configuring/services/secrets),
[Cloud Billing budget guide](https://cloud.google.com/billing/docs/how-to/budgets),
and [Vercel rewrite guide](https://vercel.com/docs/routing/rewrites). Dashboard
labels must be rechecked at execution time; this ticket does not invent or
freeze click paths.

## Local Docker evidence

On 2026-10-16, commit
`912e2085370494071b8df6ded4e9512402f1275d` was validated with the temporary
image `nebula-gcp001-api-dockercheck:912e208` and container
`nebula-gcp001-api-dockercheck-912e208` on loopback port `18081`.

- The backend Dockerfile built successfully.
- The API-only container used explicit dummy settings, the injected `PORT`, and
  `RUNNERS_ENABLED=false`; no `.env` file or production secret was used.
- `/live` returned `200` with `{"status":"ok"}`.
- `/ready` returned `503` with `{"detail":"Database is unavailable"}` because
  the test deliberately used an unreachable dummy database.
- The temporary container and image were removed and their absence was
  verified; the Git worktree remained clean.

This proves local image build, API startup, `PORT`, liveness, and readiness
failure behavior. It does not prove Supabase connectivity: positive
database-backed readiness remains unproven until the later deployed acceptance
gate.

## Cost-risk warning

Cloud Run Free Tier is a billing-account usage discount, not a zero-cost
guarantee. Public requests can consume the allowance. CPU, memory, probes,
internet egress, Artifact Registry storage, Cloud Build, Secret Manager,
logging, currency conversion, taxes, and optional networking can incur costs.
`maxScale=2` limits capacity but is not a monetary cap. Minimum instances must
remain zero and instance-based billing is outside this profile. The owner must
recheck current pricing immediately before any external authorization.

## Future public acceptance criteria

No GCP completion or public-browser claim is allowed until owner-authorized
evidence demonstrates all of the following:

- the deployed revision is identified by immutable image digest;
- the stable Cloud Run HTTPS origin serves bounded `200` JSON from `/live`;
- `/ready` returns `200` only with reachable PostgreSQL and bounded `503`
  otherwise, without exposing configuration;
- the service configuration still has request-based CPU, `minScale=0`, the
  reviewed maximum, `RUNNERS_ENABLED=false`, and no transaction-signing key;
- the Vercel browser URL remains same-origin under `/api/v1/*`, maps upstream
  to `/v1/*`, and does not cache authentication or per-user responses;
- allowed Origin succeeds and missing/wrong Origins are rejected;
- access tokens never enter browser storage and refresh-cookie flags/path,
  rotation, replay-family revocation, and logout pass in a real browser;
- the API, laptop runners, and deterministic fixture worker are identified
  separately in the evidence; and
- no real GPU, continuous hosted runner, production-readiness, SLA, or fully
  hosted end-to-end claim is made.

## Rollback

Cloud Run rollback and Vercel rollback are separate owner-approved actions:

1. Stop the supervised laptop worker and all five runners so no new lease or
   transaction work begins during routing changes.
2. Route Cloud Run traffic back to the last known-good immutable revision.
3. Re-run `/live`, `/ready`, exact-origin, cookie, refresh/logout, and browser
   smoke checks because revision rollback does not validate dependencies.
4. If the upstream remains unacceptable, restore the previous known-good
   Vercel deployment/rewrite; do not insert a guessed or placeholder origin.
5. Record sanitized revision, digest, routing, health, and outcome evidence.
6. Disable or remove cost-bearing GCP resources only after explicit owner
   approval and the evidence-retention decision.

## OCI switch-back

Switch-back happens against the original canonical repository and the
owner-controlled Vercel project, not by recreating OCI files here:

1. Confirm the canonical OCI HTTPS origin is deployed and independently passes
   public `/live` and `/ready` checks.
2. Confirm its `FRONTEND_URL`, cookie attributes, exact-Origin enforcement, and
   credentialed CORS still match the unchanged Vercel browser origin.
3. Obtain explicit owner approval for the exact rewrite-only cutover.
4. Change the Vercel `/api/v1/*` upstream from the verified Cloud Run origin to
   the verified OCI origin, preserving `/v1/*` mapping and cache opt-out.
5. Run allowed/wrong-origin and genuine browser-auth acceptance checks.
6. Preserve sanitized switch-back evidence and the previous Vercel deployment
   as the immediate rollback route.
7. Stop or remove GCP resources only after the observation window and separate
   owner authorization.

Do not copy `deploy/oci/` or `scripts/be002_production_auth_wizard.sh` into this
snapshot. Do not mark BE-002, OPS, QA, or release tickets complete from this
adapter contract.
