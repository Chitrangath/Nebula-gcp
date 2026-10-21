# GCP-002 Deployment-Readiness Research Addendum

**Research and access date:** 2026-10-16

**Source policy:** official Google Cloud and Vercel documentation only

**Scope:** deployment-readiness evidence; no cloud, Vercel, DNS, billing, IAM,
secret, build, registry, or deployment action was performed

## Decision summary

The approved demonstration topology is feasible with Vercel serving the
frontend, a public Cloud Run service serving only the FastAPI API, Supabase
serving PostgreSQL, and the owner laptop running the fixture worker and five
controlled runners only during supervised demonstrations. Cloud Run must keep
request-based billing, zero minimum instances, and a low maximum instance
count. It must never receive a runner signing key or run Nebula's continuous
runner loops.

The public Cloud Run origin is an upstream for the existing Vercel
same-origin `/api/v1/*` interface. A Vercel rewrite does not make the generated
`run.app` origin private: Google documents public Cloud Run access as disabling
the Invoker IAM check (recommended) or granting `roles/run.invoker` to
`allUsers`. Application authentication, authorization, CSRF/origin controls,
and rate/abuse handling therefore remain mandatory at the FastAPI boundary.
[Google: public Cloud Run access](https://docs.cloud.google.com/run/docs/authenticating/public)

## Deployment gates supported by current sources

### 1. Project, billing, region, and APIs

The owner must approve the project, attached billing account, region, and each
API before enablement. Enabling APIs requires
`serviceusage.services.enable`; it is an administrative setup permission, not
a runtime permission. The narrow image-first path needs the Cloud Run Admin,
Artifact Registry, and Secret Manager APIs. Cloud Build is needed only if the
owner selects a Google-hosted build. A source deployment can implicitly build
and create an Artifact Registry repository, so it is less suitable than an
explicit build/repository/review sequence for this gated demonstration.
[Google: deploy services from source](https://docs.cloud.google.com/run/docs/deploying-source-code)

Billing controls must precede public exposure. Alerts-only budgets notify but
do **not** cap usage or charges. Where available and suitable, a spend-cap
budget can pause eligible Cloud Run usage, but enforcement is not instantaneous
and an enforced cap makes Cloud Run services return `5xx`. The owner must treat
that availability tradeoff as an explicit decision.
[Google: budgets and alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets),
[Google: spend-cap budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps),
[Google: Cloud Run billing settings](https://docs.cloud.google.com/run/docs/configuring/billing-settings)

### 2. Identities and secrets

Cloud Run distinguishes the deployer identity from the service identity used
by a running revision. The runtime should use a dedicated user-managed service
account, not the deployer account and not a downloaded key. Google explicitly
warns not to set `GOOGLE_APPLICATION_CREDENTIALS` on Cloud Run when using a
service identity. For this API-only profile, runtime Google permissions should
be limited to `roles/secretmanager.secretAccessor` on the exact required
secrets; it needs no build, deploy, IAM, runner, or chain-signing permission.
[Google: Cloud Run service identity](https://docs.cloud.google.com/run/docs/securing/service-identity),
[Google: Cloud Run IAM roles](https://docs.cloud.google.com/run/docs/reference/iam/roles)

Google recommends Secret Manager for sensitive Cloud Run configuration. Secret
environment variables are resolved before an instance starts, and Google
recommends pinning them to a numbered version rather than `latest`. Deployment
checks that the runtime service account can access referenced secrets. Nebula's
`DATABASE_URL` and `JWT_SECRET` should therefore reference owner-approved,
numbered versions; values must not enter Git, image layers, build arguments,
logs, wizard output, or evidence documents.
[Google: configure Cloud Run secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets)

### 3. Request lifecycle and API-only enforcement

With request-based billing, CPU is allocated during request processing rather
than for the full instance lifecycle. Zero minimum instances permits scale to
zero; configured minimum instances incur idle cost. A low maximum instance
count reduces public-traffic blast radius, but it is not a hard financial cap:
Cloud Run can briefly exceed the configured maximum during rapid surges, and
old and new revisions can each have their own maximum during a deployment.
[Google: billing settings](https://docs.cloud.google.com/run/docs/configuring/billing-settings),
[Google: minimum instances](https://docs.cloud.google.com/run/docs/configuring/min-instances),
[Google: maximum instances](https://docs.cloud.google.com/run/docs/configuring/max-instances-limits)

These lifecycle properties are incompatible with a claim that Cloud Run hosts
continuous Nebula runners for free or reliably. GCP-002 must preserve
`RUNNERS_ENABLED=false`, omit all runner containers/jobs/worker pools and
runner secrets, and reject any materialized profile that enables them. The
owner laptop remains responsible for the worker and five controlled runners.

### 4. Public health acceptance

Cloud Run HTTP probes use HTTP/1 and treat `2xx` or `3xx` as success. Startup
probe success makes the instance eligible for traffic; readiness-probe failure
stops new routing without terminating the instance. Probe endpoints are
externally reachable on a public service and therefore must not reveal secret
or diagnostic detail. Probe execution allocates CPU and is billed for CPU and
memory, although it has no request charge.
[Google: Cloud Run health checks](https://docs.cloud.google.com/run/docs/configuring/healthchecks)

For Nebula acceptance, test both meanings independently after deployment:

- `/live` returns a minimal `200` response proving the API process is alive.
- `/ready` returns `200` only when the deployed API can reach the approved
  Supabase PostgreSQL database; a `503` is the correct failure result.
- Neither response contains credentials, connection strings, stack traces, or
  internal configuration.

The earlier local Docker evidence establishes that the backend image builds,
honors the injected `PORT`, and serves `/live` as `200`. Its deliberate dummy,
unreachable database produced `/ready` as `503`; it does not establish
database-backed readiness and cannot replace the deployed Supabase check.

### 5. Vercel same-origin cutover

Vercel external rewrites proxy to an external origin without changing the URL
shown to the browser. This supports keeping browser calls on
`/api/v1/:path*` while the upstream destination becomes the reviewed Cloud Run
HTTPS origin. The materialized rewrite must contain the exact owner-approved
origin and preserve the path mapping; no bearer token, cookie, credential, or
secret belongs in the destination.
[Vercel: rewrites](https://vercel.com/docs/routing/rewrites)

Caching requires an explicit GCP-002 control. Vercel announced that new
projects honor external-origin cache headers by default from April 2026 and
documents `x-vercel-enable-rewrite-caching: 0` as the path-level opt-out.
Authenticated `/api/v1/*` traffic must use that opt-out and suitable origin
`Cache-Control` headers; no authentication or user-specific API response may
be served from shared CDN cache.
[Vercel: external-origin cache behavior](https://vercel.com/changelog/vercels-cdn-now-respects-cache-control-headers-from-external-origins-by-default)

Cutover is an owner-controlled release, not a configuration side effect:
validate the Cloud Run origin directly, materialize and review the rewrite,
deploy a Vercel preview/staged build, run the real-browser auth smoke, then
promote it. Vercel documents preview inspection/testing before promotion.
[Vercel: promote preview to production](https://vercel.com/docs/deployments/promote-preview-to-production)

### 6. Rollback and switch-back

Retain the last known-good immutable Cloud Run image digest and revision.
Cloud Run can move all traffic to a prior revision, but Google warns that this
traffic change is immediate and does not rerun deployment health checks or
verify external dependencies. Rollback acceptance must therefore repeat
`/live`, database-backed `/ready`, and browser-auth checks.
[Google: Cloud Run rollouts and rollback](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)

Retain the previous Vercel production deployment/rewrite. Vercel Instant
Rollback repoints domains to an earlier production deployment without a
rebuild; its embedded configuration can be stale, and changed environment
variables are not rebuilt. After rollback, Vercel disables automatic
production-domain assignment until rollback is undone. The owner must verify
the exact upstream destination and auth behavior after rollback.
[Vercel: Instant Rollback](https://vercel.com/docs/instant-rollback)

OCI switch-back is architectural, not automatic: remove the GCP rewrite only
through an owner-approved Vercel release, restore the previously verified OCI
origin/configuration from the original repository, rerun health and browser
auth acceptance, then set Cloud Run traffic to zero or remove the temporary
service in a separately authorized cleanup. Nothing in the GCP copy replaces
OCI as the original repository's canonical long-term target.

## Cost and abuse threat checklist

| Exposure | Readiness control |
| --- | --- |
| Public request flood | Low service-level maximum instances, application auth and rate controls, monitoring, and owner response procedure. A maximum can be briefly exceeded and is not a cost ceiling. |
| Cloud Run compute/requests | Request-based billing, zero minimum instances, 512 MiB/1 vCPU starting profile, short timeout, no background runner work. |
| Health probes | Minimal responses and conservative periods; include probe CPU/memory use in cost review. |
| Supabase and other internet egress | Select region after owner latency/cost review; include response, database, RPC, and storage traffic in estimates. Cloud Run internet egress is billable outside allowances. [Google: Cloud Run pricing](https://cloud.google.com/run/pricing) |
| Image registry | Region-align Artifact Registry and Cloud Run, deploy by immutable digest, and retain only current plus rollback images. Storage and some transfer are billable. [Google: Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing) |
| Build | Prefer a separately reviewed image build. Cloud Build minutes, workers, logs, and transfer can cost money if Cloud Build is selected. [Google: Cloud Build pricing](https://cloud.google.com/build/pricing) |
| Secrets | Pin numbered versions; limit runtime access to exact secrets; account for active-version storage and access operations. [Google: Secret Manager pricing](https://cloud.google.com/secret-manager/pricing) |
| Logs | Never log secrets/tokens/request bodies; set retention and exclusions deliberately. Ingestion and retention beyond allowances can cost money. [Google: Observability pricing](https://cloud.google.com/products/observability/pricing) |
| Vercel proxy cache | Explicitly opt authenticated API paths out of rewrite caching and verify response headers in the browser smoke. |
| Budget controls | Configure alerts before exposure; understand that alerts do not cap spend and enforced spend caps intentionally trade availability for cost containment. |

## GCP-002 readiness conclusion

Deployment may proceed only under a later, explicit owner-authorized ticket
after all placeholders are replaced with reviewed values and the owner has
approved billing, region, APIs, identities, exact secret names and numbered
versions, immutable image digest, public invocation, maximum instances, health
acceptance, Vercel rewrite, rollback targets, and cost-response ownership.
GCP-002 itself remains local and non-mutating.
