# GCP Demo Hosting Feasibility and Design Record

**Research date:** 2026-10-16
**Decision status:** research and proposed design only; no adapter has been
implemented and no cloud or Vercel action has been performed.

## Decision

Cloud Run is feasible as a **temporary, lightweight, public FastAPI demo
host**. A Cloud Run service has a stable, Google-managed HTTPS service URL and
can serve a containerized web API. The recommended demo profile is
request-based billing, zero minimum instances, a deliberately low maximum
instance count, and the existing Vercel same-origin `/api/v1/*` rewrite.
Google documents both the stable HTTPS URL and public unauthenticated access
model for Cloud Run services in [Invoke with an HTTPS request](https://docs.cloud.google.com/run/docs/triggering/https-request).

This recommendation does **not** extend to Nebula's continuous scheduler,
receipt, assignment, settlement, event, or reconciliation work. Under
request-based billing, CPU is allocated only while a request is being
processed; a service with no traffic can scale to zero. Instance-based billing
and minimum instances can enable background work, but they incur lifecycle or
idle charges and still do not make an instance permanent. Google describes
these differences in [Cloud Run billing settings](https://docs.cloud.google.com/run/docs/configuring/billing-settings),
[minimum instances](https://docs.cloud.google.com/run/docs/configuring/min-instances),
and [autoscaling](https://docs.cloud.google.com/run/docs/about-instance-autoscaling).

Therefore, during a demonstration:

- Cloud Run hosts only the lightweight FastAPI request path.
- The deterministic fixture worker and deliberately controlled runner work
  remain on the owner laptop.
- No always-on runners, real GPU inference, production readiness, production
  SLA, or fully hosted end-to-end journey may be claimed.
- OCI remains the original project's canonical long-term hosting target. This
  GCP profile is isolated, temporary, and reversible.

## Scope and evidence boundary

The prior NET-003 evidence proves a connected Arbitrum Sepolia journey through
the FastAPI application, PostgreSQL, five independent runners, the deployed
contract, and a deterministic fixture worker. It does not prove that Cloud Run
can continuously host those runners, a public browser journey, or real GPU
inference. This design changes only the hosting adapter; it does not change the
**AI user**, **GPU provider**, **GPU node**, **worker**, **worker signer**,
**lease**, **job fingerprint**, **proof envelope**, **verifier**, **verdict**,
or **settlement** meanings in `CONTEXT.md`.

The following are explicitly unchanged and outside this design:

- Solidity, contract roles and configuration, Arbitrum Sepolia deployment,
  escrow, proof, verification, and settlement behavior;
- backend protocol/business logic, database schema, job/lease state machines,
  worker protocol, and PoAE evidence rules;
- the browser-auth security model and token ownership;
- the PRD and Development Plan; and
- the original repository's OCI files and canonical OCI direction.

## Cloud Run fit for the FastAPI service

Every Cloud Run service receives a stable HTTPS endpoint on `run.app`, managed
TLS, and regional multi-zone service placement. The service URL remains the
load-balanced interface while immutable revisions and their traffic allocation
change behind it. See [What is Cloud Run](https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run),
[deployment options and resource model](https://docs.cloud.google.com/run/docs/resource-model),
and [revisions](https://docs.cloud.google.com/run/docs/managing/revisions).

The existing backend image is structurally compatible with a Cloud Run
service if the service's container port is explicitly set to `8000`: it runs a
non-root user and Uvicorn listens on `0.0.0.0:8000`. Cloud Run injects `PORT`
and defaults to `8080`, but permits a configured port; its ingress container
must listen on `0.0.0.0`. The platform terminates TLS before forwarding the
request to the container. These requirements are documented in the
[container runtime contract](https://docs.cloud.google.com/run/docs/container-contract).
This observation is static only; no image was built or deployed in this phase.

The public demo needs the service to allow unauthenticated invocation because
an ordinary Vercel external rewrite does not mint a Google identity token.
Google's current recommended public-access method is to disable the Cloud Run
Invoker IAM check; granting `roles/run.invoker` to `allUsers` remains the
documented alternative. Either permits HTTP invocation only and must not grant
any runtime, build, deployment, secret, or project privilege. See
[Allowing public access](https://docs.cloud.google.com/run/docs/authenticating/public).
Nebula application authentication and authorization remain responsible for
protected routes.

The generated `run.app` service URL is sufficient for the Vercel upstream.
No custom domain, DNS record, external load balancer, or certificate is needed
for the GCP experiment. Avoiding those resources also avoids extra cost and
switch-back state.

## Account, billing, and cost exposure

### Required owner setup

Cloud Run's Free Tier still requires an active Cloud Billing account linked to
the selected Google Cloud project. Google states that a billing account is
required to access the Free Tier in [Google Cloud Free Program](https://docs.cloud.google.com/free/docs/free-cloud-features).
The owner, not an agent, must create or select the account and project, link
billing, inspect the payment state, enable only the required APIs, approve IAM,
and authorize every operation that can create a charge.

The eventual minimal API set should be reviewed from the actual adapter before
use. It is expected to include Cloud Run Admin, Artifact Registry, Secret
Manager, and, only if Google performs the build, Cloud Build. API enablement,
repository creation, image upload, secret creation, IAM grants, and service
creation are all future owner-approved actions, not outcomes of this record.

### Free Tier and regions

For **request-based billing**, the current monthly Cloud Run allowance is:

- 2 million requests;
- 180,000 vCPU-seconds;
- 360,000 GiB-seconds of memory; and
- 1 GiB outbound data transfer from North America.

These limits are monthly, aggregate across projects by billing account, and
are applied as a spending-based discount using Tier 1 (`us-central1`) pricing;
usage beyond them is charged. See the official [Cloud Run pricing table](https://cloud.google.com/run/pricing)
and [Google Cloud Free Tier table](https://docs.cloud.google.com/free/docs/free-cloud-features).

Tier 1 Cloud Run regions currently listed by Google are `africa-south1`,
`asia-east1`, `asia-northeast1`, `asia-northeast2`, `asia-south1`,
`asia-southeast3`, `asia-southeast4`, `europe-north1`, `europe-north2`,
`europe-southwest1`, `europe-west1`, `europe-west4`, `europe-west8`,
`europe-west9`, `me-west1`, `northamerica-south1`, `us-central1`, `us-east1`,
`us-east4`, `us-east5`, `us-south1`, `us-west1`, and `us-west8`. The remaining
listed regions are Tier 2 and have higher rates. The Free Tier is not a
region-limited VM entitlement: its discount is based on Tier 1 pricing, so a
Tier 2 location can consume the dollar-equivalent allowance faster.

The default recommendation is `us-central1` only if its latency to the chosen
PostgreSQL project and the expected demonstrator is acceptable. Otherwise use
the nearest Tier 1 region after measuring database latency. Region selection
must be an explicit owner decision because service location is part of the
cost, latency, data-location, and rollback record.

### Every relevant cost path

Free Tier is an allowance, not a guarantee of a zero invoice. The owner must
review all of these paths before deployment:

| Cost source | Exposure and guardrail |
| --- | --- |
| Cloud Run requests, CPU, and memory | Charged after the monthly billing-account allowance. Use request-based billing, `min-instances=0`, a low explicit maximum, and a measured 512 MiB starting profile. Public traffic or abuse can consume the allowance. Google notes that maximum-instance limits can be temporarily exceeded during spikes or deployments, so the maximum is not a hard cost cap; see [maximum instances](https://docs.cloud.google.com/run/docs/configuring/max-instances-limits). |
| Minimum instances / instance-based billing | Minimum instances incur idle or lifecycle charges. Keep minimum instances at zero and do not select instance-based billing for this API-only profile. |
| Health probes | Probe execution is billed for CPU and memory consumption, although it has no request charge. Use only useful, low-frequency probes and include them in estimates. |
| Network transfer | Responses to Vercel, RPC/storage traffic, and other internet egress can be billable. Only 1 GiB North America outbound transfer is included in the quoted Cloud Run allowance. Avoid a VPC connector. |
| Serverless VPC Access | Connector instances are billed as Compute Engine VMs, have a minimum of two instances, and do not scale in. It is unnecessary for public Supabase/RPC endpoints and prohibited by this low-cost profile. See [Serverless VPC Access](https://docs.cloud.google.com/vpc/docs/serverless-vpc-access). |
| Artifact Registry | The first 0.5 GiB-month of storage is free per billing account; excess storage, outbound transfer, and optional vulnerability scanning can cost money. Retain only the current and rollback images. See [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing). |
| Cloud Build | Build minutes and build egress can be billable. The current promotional allowance is 2,500 `e2-standard-2` build-minutes per billing account per month and is subject to change. See [Cloud Build pricing](https://cloud.google.com/build/pricing). |
| Secret Manager | The current allowance is six active secret versions, 10,000 access operations, and three rotation notifications per billing account per month; excess versions/access/notifications cost money. See [Secret Manager pricing](https://cloud.google.com/secret-manager/pricing). |
| Logging and monitoring | Cloud Logging storage beyond its free ingestion allotment and extended retention can cost money. Avoid debug/request-body logging and never log secrets or tokens. See [Google Cloud Observability pricing](https://cloud.google.com/products/observability/pricing). |
| Optional GCP products | GPUs, Cloud SQL, load balancers, Cloud DNS, custom-domain products, Cloud Scheduler, Cloud Tasks, Pub/Sub, worker pools, Cloud Run Jobs, and VPC resources are not part of this profile. Adding any requires separate design, pricing review, and owner authorization. |
| Non-Google dependencies | Supabase, Vercel, Arbitrum RPC, R2/IPFS, and any monitoring provider have separate quotas and billing. Google budgets do not cap them. |

Use Cloud Billing reports and alerts. If the owner's account supports Cloud
Billing spend caps, apply a deliberately low project-level cap after reviewing
its effect: hitting it pauses Cloud Run workloads and causes service failures,
and it does not cover resources such as connector VMs. The current behavior is
documented in [Cloud Billing spend caps](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)
and [Cloud Run billing settings](https://docs.cloud.google.com/run/docs/configuring/billing-settings).
A maximum instance count reduces blast radius but is not a monetary ceiling.
Currency conversion, taxes, shared billing-account usage, and price changes can
also change the final invoice.

## Secrets and least-privilege identities

Do not put `DATABASE_URL`, `JWT_SECRET`, private keys, credential-bearing RPC
URLs, R2 credentials, tokens, or service-account key JSON in Git, a container
image, build arguments, build logs, evidence, or Vercel routing configuration.
Cloud Run recommends Secret Manager and can expose a secret as a mounted file
or environment variable. Mounted secrets fetch the selected value when read;
environment-variable secrets are resolved when an instance starts, for which
Google recommends pinning a numbered version rather than `latest`. See
[Configure secrets for Cloud Run services](https://docs.cloud.google.com/run/docs/configuring/services/secrets).

The proposed identities are deliberately separate:

1. **Owner/bootstrap identity** — links billing, enables APIs, creates the
   project-level resources, and delegates narrower roles. It is not the
   routine runtime identity.
2. **Deployer identity** — can update the named Cloud Run service, read only
   the selected Artifact Registry repository, and act as only the selected
   runtime identity. Google's documented minimal container-deployment roles
   are Cloud Run Developer (`roles/run.developer`), Artifact Registry Reader
   (`roles/artifactregistry.reader`), and Service Account User
   (`roles/iam.serviceAccountUser`) on the service identity. See
   [Cloud Run IAM roles](https://docs.cloud.google.com/run/docs/reference/iam/roles).
3. **Build identity** — a distinct user-managed service account if Cloud Build
   is used, with only the repository/log/build permissions required by the
   chosen build. Google recommends a user-managed account because defaults can
   be broader than necessary; see [Run builds with a user-managed service account](https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts).
4. **Runtime identity** — a dedicated user-managed service account with no
   project-wide Editor role, no deploy/build role, no downloadable key, and
   Secret Manager Secret Accessor (`roles/secretmanager.secretAccessor`)
   granted on only the exact required secrets. It receives no chain-signing
   secret in the API-only profile and `RUNNERS_ENABLED` remains false. Google
   recommends user-managed minimal service identities and explicitly warns
   against setting `GOOGLE_APPLICATION_CREDENTIALS` on Cloud Run; see
   [Cloud Run service identity](https://docs.cloud.google.com/run/docs/securing/service-identity).
5. **Public invoker** — unauthenticated invocation of only the Cloud Run HTTP
   service. This is not an IAM identity used by the application and grants no
   access to Secret Manager or other project resources.

Prefer secret environment references pinned to versions for existing settings
that the FastAPI configuration already reads from environment variables.
Rotation is a new revision operation: create a new version, deploy a revision
referencing it, validate, shift traffic, and then disable the old version after
the rollback window. The owner enters secret values through hidden/local or
cloud-console inputs; the future wizard must never echo or persist them in the
repository.

## Request lifecycle and runner limitation

Cloud Run services are request-driven and their instances are ephemeral:

- With request-based billing, CPU is allocated only while an instance is
  starting, stopping, or processing a request. After the response, CPU can be
  disabled or severely limited.
- With no minimum instances, an idle service scales to zero; the next request
  creates an instance and may experience cold-start latency.
- A request times out after 5 minutes by default and can be configured only up
  to 60 minutes. A timeout returns `504` but does not necessarily stop the
  container's work, so using a long request as a runner surrogate is unsafe.
  See [Cloud Run request timeouts](https://docs.cloud.google.com/run/docs/configuring/request-timeout).
- Instance-based billing allocates CPU for the instance lifecycle, but the
  autoscaler can still terminate an unneeded instance. Keeping a minimum
  instance running incurs charges, and a terminating instance gets only a
  short shutdown grace period.
- In-memory state and the writable filesystem belong to an instance and must
  not be treated as durable workflow storage.

Nebula's scheduler, receipt, assignment, settlement, event, and reconciliation
runners are independent background loops with database and chain side effects.
They cannot depend on incidental HTTP traffic, an open request, a warm
instance, or a local filesystem. Artificial keep-alive requests would neither
provide correct lifecycle guarantees nor truthfully preserve a free profile.
Cloud Run Jobs, worker pools, scheduled triggers, push queues, or a redesigned
idempotent tick interface are separate architectures with separate billing and
security reviews; none is authorized here.

For this demo profile, `RUNNERS_ENABLED=false` is an invariant. The owner
starts the existing controlled runners and deterministic fixture worker on the
owner laptop only for a supervised demonstration, then stops them. Any
transaction-signing key remains owner-controlled and absent from the Cloud Run
API revision.

## Low-memory image and deployment options

No build or deployment was run. The future implementation should compare
these options using a local static contract and image test before the owner
authorizes external work:

1. **Recommended: existing Dockerfile, Cloud Build, Artifact Registry, then
   deploy-by-digest.** Submit only the `backend/` build context, retain its
   frozen `uv.lock`, multi-stage slim image, non-root user, and `--no-dev`
   dependency install. Keep worker/PyTorch, frontend/node dependencies, test
   caches, and local artifacts out of the context. Building and deploying are
   separate interfaces, which makes the image digest reviewable and rollback
   deterministic.
2. **Acceptable fallback: owner-built `linux/amd64` image pushed to Artifact
   Registry.** Cloud Run requires a Linux x86-64-compatible image (or a
   multi-architecture manifest containing `linux/amd64`). This avoids Cloud
   Build minutes but moves Docker availability, registry authentication, and
   upload egress to the owner machine.
3. **Not preferred: deploy from source.** Google can build Python source or a
   Dockerfile using Cloud Build and Artifact Registry, but its convenience
   interface gives less control over the build. See [Deploy services from source](https://docs.cloud.google.com/run/docs/deploying-source-code).

Start measurement at 512 MiB memory, one vCPU, request-based billing, zero
minimum instances, and an explicit low maximum instance count. Cloud Run's
second-generation minimum is 512 MiB and the service default is 512 MiB; an
instance that exceeds its limit is terminated. See [Cloud Run memory limits](https://docs.cloud.google.com/run/docs/configuring/services/memory-limits).
Do not advertise 512 MiB as proven sufficient until the actual locked image
passes cold-start, `/live`, `/ready`, authentication, and representative API
smoke under that limit. Bound concurrency and maximum instances according to
the Supabase connection limit found at implementation time.

## Vercel same-origin browser interface

The browser interface remains exactly:

```text
Browser at https://<frontend-origin>
  -> /api/v1/:path*
  -> Vercel external rewrite
  -> https://<cloud-run-service>.run.app/v1/:path*
```

Vercel documents that an external rewrite forwards to another origin without
changing the browser-visible URL in [Rewrites on Vercel](https://vercel.com/docs/routing/rewrites).
That is the required seam: the browser continues to see the Vercel origin and
never learns a GCP-specific application interface.

The eventual rewrite must be ordered before the SPA fallback and must
explicitly disable caching for `/api/v1/:path*` with
`x-vercel-enable-rewrite-caching: 0`. Vercel announced that new projects can
honor external-origin cache headers by default, so the explicit opt-out avoids
accidentally caching authentication or per-user responses; see the
[Vercel external-origin caching change](https://vercel.com/changelog/vercels-cdn-now-respects-cache-control-headers-from-external-origins-by-default).
The backend's existing `Cache-Control: no-store` responses remain necessary.

No browser code, auth route, cookie, CORS, or origin check changes:

- access tokens stay only in JavaScript module memory;
- refresh tokens remain host-only, `HttpOnly`, `Secure`,
  `SameSite=Strict`, and `Path=/api/v1/auth`;
- verify, refresh, and logout continue to require exact
  `Origin == FRONTEND_URL`;
- `FRONTEND_URL` remains the exact deployed Vercel origin with no path;
- credentialed CORS continues to allow only that origin; and
- the browser must not call the `run.app` URL directly.

The rewrite changes upstream hosting, not the security interface. The public
Cloud Run URL is still directly reachable, so deployment acceptance must test
both the allowed frontend origin and rejection of missing/wrong origins. A
green direct `curl` is not browser-auth evidence.

## Health, release, rollback, and OCI switch-back

### Public health and acceptance

The repository already exposes `/live` for process liveness and `/ready` for a
database reachability check. The future deployment must:

1. keep the Cloud Run service's deployment health check enabled;
2. configure a startup probe compatible with the existing `/live` endpoint;
3. verify `GET https://<service>.run.app/live` returns bounded `200` JSON;
4. verify `/ready` returns `200` only when PostgreSQL is reachable and a
   bounded `503` otherwise;
5. verify no health response exposes configuration or credentials;
6. test the Vercel rewrite, exact allowed/disallowed Origin behavior, cookie
   flags/path, refresh rotation, logout, and a real-browser auth smoke; and
7. record only sanitized public evidence under `docs/evidence/`.

Cloud Run supports startup, liveness, and readiness probes, but passing a
startup probe must itself imply that the container can safely receive traffic;
see [Cloud Run health checks](https://docs.cloud.google.com/run/docs/configuring/healthchecks).
Platform probes supplement rather than replace the public `/live` and `/ready`
acceptance checks.

### Revision release and rollback

Every configuration or image change creates an immutable revision. Deploy a
candidate with no production traffic, identify it by image digest/revision,
run the permitted checks, and only then shift traffic. Preserve the last known
good revision and digest. Rollback sends 100% of traffic to that revision.
Google warns that traffic rollback is immediate and does not re-run deployment
health checks or validate external dependencies, so `/live`, `/ready`, exact
origin, and browser-auth smoke must be rerun after rollback. See
[Cloud Run rollouts and rollbacks](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration).

The stable service URL means a revision rollback should not require a Vercel
rewrite change. Do not use revision-tag URLs as the permanent Vercel upstream.

### OCI switch-back

OCI remains canonical in the original project. A switch-back requires:

1. owner confirmation that the canonical OCI HTTPS origin is deployed and
   passes public `/live` and `/ready` checks;
2. confirmation that its `FRONTEND_URL` equals the unchanged Vercel origin and
   that its existing cookie/CORS/origin security configuration is intact;
3. an owner-approved Vercel rewrite-only change from the stable Cloud Run
   service URL back to the canonical OCI HTTPS origin;
4. deployed allowed/wrong-Origin and real-browser authentication smoke;
5. sanitized switch-back evidence and a recorded rollback route to the prior
   Vercel deployment; and
6. after the observation window and explicit approval, removal or disabling of
   GCP resources that can serve traffic or accrue cost.

Do not copy or recreate `deploy/oci/` or
`scripts/be002_production_auth_wizard.sh` in this intentionally reduced GCP
snapshot. Switch-back is an operational action against the original canonical
repository and owner-controlled Vercel project, not an OCI restoration in this
copy.

## Proposed provider-isolated layout (not implemented)

```text
deploy/gcp-demo/                    # reviewed Cloud Run/build/IAM inputs; no secrets
scripts/gcp_demo_owner_wizard.sh    # guarded owner-only account/deploy/Vercel steps
docs/runbooks/GCP_DEMO_HOST.md      # deploy, verify, stop, rollback, OCI switch-back
docs/evidence/GCP_DEMO_*.md         # sanitized observed facts only
```

The hosting **seam** is the stable FastAPI container/runtime interface and the
same-origin Vercel rewrite. GCP is a provider-specific **adapter** at that seam,
not a second FastAPI application. This keeps the module deep: callers retain a
small interface (`/api/v1/*`, `/live`, `/ready`, environment configuration),
while provider-specific build, identity, revision, and rollback details remain
local to `deploy/gcp-demo/` and its runbook. OCI and GCP are then two real
adapters without layering one on the other.

Expected responsibilities:

- `deploy/gcp-demo/`: declarative, reviewable values and templates for the
  API-only Cloud Run service, build/image interface, identity names, resource
  bounds, probes, `RUNNERS_ENABLED=false`, and rollback metadata. It contains
  references to secrets, never secret values.
- `scripts/gcp_demo_owner_wizard.sh`: human-only prerequisite checks, hidden
  secret input, explicit confirmation before billable/external actions,
  dry-run/plan visibility, public health/auth verification, sanitized evidence,
  stop/rollback, and OCI switch-back guidance. It must default to no external
  mutation and refuse xtrace.
- `docs/runbooks/GCP_DEMO_HOST.md`: exact owner commands, expected output,
  cost checks, failure handling, verification, teardown, rollback, and
  switch-back.
- `docs/evidence/GCP_DEMO_*.md`: dated public values such as project-neutral
  revision/image digests, service URL, settings, checks, and outcomes; never
  credentials, tokens, private URLs, wallet keys, or unredacted logs.

The deletion test is intentional: deleting `deploy/gcp-demo/`, the GCP wizard,
runbook, evidence, and Vercel rewrite change removes the experiment without
spreading GCP conditionals through protocol or application code.

## Exact next implementation slice — do not begin in this phase

The next authorized slice should be **GCP-001: local API-only adapter contract**:

1. write failing static tests that assert an isolated `deploy/gcp-demo/`
   configuration uses request-based billing, zero minimum instances, a low
   maximum, 512 MiB initial memory, port `8000`, public `/live` and `/ready`, a
   dedicated runtime identity, Secret Manager references, and
   `RUNNERS_ENABLED=false`;
2. add the minimum declarative deployment/build templates needed to make those
   tests pass, pinned to an image digest input and containing no project,
   account, URL, or secret values;
3. add static checks proving the proposed Vercel rewrite maps
   `/api/v1/:path*` to `/v1/:path*`, precedes the SPA fallback, and disables
   API rewrite caching;
4. add a non-mutating `--check`/`--plan` shell path for the future owner wizard
   and document its expected output in the runbook; and
5. run syntax, formatting, secret-scan, documentation-link, and focused static
   contract tests only.

GCP-001 must stop before authentication, API enablement, IAM mutation, secret
creation, image upload, deployment, Vercel change, DNS change, or any other
external account action. A later owner-authorized slice can execute the
reviewed wizard and record observed evidence.

## Phase skill usage

### Discovered skills

`solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`,
`diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`,
`improve-codebase-architecture`, `handoff`, `ask-matt`,
`setup-matt-pocock-skills`, `teach`, and `wizard`.

### Applied skills

1. **research** — current Cloud Run, Google Cloud Billing/IAM/build/secret
   facts and Vercel rewrite behavior were checked against first-party Google
   and Vercel sources, with direct links next to the resulting claims.
2. **codebase-design** — the GCP work is proposed as a provider-specific
   adapter at the existing container and same-origin routing seam, preserving
   a small runtime interface and localizing provider complexity.
3. **domain-modeling** — the design was stress-tested against `CONTEXT.md` and
   preserves the distinct AI user, GPU provider, GPU node, worker, worker
   signer, proof envelope, verifier, verdict, and settlement concepts. No new
   domain term was resolved, so `CONTEXT.md` was not changed.

### Not applied

- **solidity-foundry-security** — no contract design, code, test, ABI, or
  deployment configuration changed.
- **tdd** — this phase is research/design only; the exact test-first slice is
  specified for GCP-001 but not started.
- **code-review** — there is no originating implementation diff or completed
  adapter to review against a ticket/spec.
- **diagnosing-bugs** — no failing behavior or performance regression was
  diagnosed.
- **grill-with-docs** — no implementation plan was being challenged for
  readiness; this document establishes the research inputs and design first.
- **improve-codebase-architecture** — no refactor was authorized or performed.
- **handoff** — no session-transition document is needed; this record and the
  final task report provide the current outcome.
- **ask-matt** — skill routing was explicit in the task and `AGENTS.md`.
- **setup-matt-pocock-skills** — the skills are already installed and no setup
  was requested.
- **teach** — no teaching artifact was requested.
- **wizard** — the future owner-only wizard is designed but intentionally not
  implemented or executed in this research-only phase.

## Source freshness and verification rule

Cloud products, prices, quotas, regions, IAM roles, and Vercel routing behavior
can change. Re-open every linked official source immediately before the owner
approves GCP-001's external follow-up. No statement in this record is evidence
that a Google/Vercel account exists, billing is safe, a resource was created,
or a public deployment works.
