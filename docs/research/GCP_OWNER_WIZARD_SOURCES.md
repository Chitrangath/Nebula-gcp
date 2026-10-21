# GCP Owner-Wizard Primary Sources

**Research and access date:** 2026-10-16

**Source policy:** current first-party Google Cloud, Cloudflare R2, and Vercel
documentation only

**Scope:** source and safety record for the future owner-guided GCP-004
foundation deployment, GCP-005 Vercel/browser cutover, and GCP-006 controlled
laptop-runtime wizards. No login, account mutation, resource creation, upload,
deployment, routing change, DNS change, or credential use was performed.

## Research conclusion

The three wizards should be separate release gates, not one end-to-end deploy
script. GCP-004 may stop after direct Cloud Run and private-object acceptance;
GCP-005 may change Vercel only after sanitized GCP-004 evidence exists; and
GCP-006 may prepare laptop commands but must obtain a fresh confirmation before
starting each worker or controlled runner. Each wizard should make read-only
preflight and plan operations the default, show the exact pending mutation,
require an immediate owner confirmation, execute only that approved operation,
and verify the resulting state before continuing.

The vendor CLIs are mutation-capable interfaces, not safe approval systems by
themselves. In particular, global `--quiet` or Cloudflare `--force` suppresses
vendor confirmation prompts. The wizards must not use either for an external
mutation. They also must not place secret material in command arguments,
terminal output, logs, evidence files, browser configuration, or Git.

## GCP-004: foundation deployment through direct acceptance

### Owner dashboards and project/billing gate

Open the relevant official page before collecting each owner decision:

| Decision | Official page |
| --- | --- |
| Select or create the isolated project | [Google Cloud project selector](https://console.cloud.google.com/projectselector2/home/dashboard) and [project creation rules](https://docs.cloud.google.com/resource-manager/docs/creating-managing-projects) |
| Review or link billing | [Cloud Billing account management](https://console.cloud.google.com/billing) and [`gcloud billing projects link`](https://docs.cloud.google.com/sdk/gcloud/reference/billing/projects/link) |
| Review budget alerts | [Budgets and alerts](https://console.cloud.google.com/billing/budgets) and [budget behavior](https://docs.cloud.google.com/billing/docs/how-to/budgets) |
| Enable only approved APIs | [API Library](https://console.cloud.google.com/apis/library) and [enable/disable services](https://docs.cloud.google.com/service-usage/docs/enable-disable) |

A project ID is immutable after creation. `gcloud projects create` creates a
project, while `gcloud billing projects link PROJECT_ID --billing-account=...`
changes which account accrues charges. These must be distinct, confirmed owner
actions rather than prerequisites the wizard performs silently.
[`gcloud projects create`](https://docs.cloud.google.com/sdk/gcloud/reference/projects/create),
[`gcloud billing projects link`](https://docs.cloud.google.com/sdk/gcloud/reference/billing/projects/link)

An alerts-only budget does **not** cap usage or spending. Spend-cap budgets can
pause eligible services, but enforcement is not instantaneous and excess cost
before enforcement remains billable. The wizard must display the selected
budget mode and require cost-risk acknowledgement; it must not describe an
alert as a hard cap.
[Google budget alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets),
[Google spend-cap budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)

`gcloud services enable SERVICE...` mutates the selected project. The wizard
must first show the active account/project and exact minimal API list, then ask
immediately before enablement. Expected APIs should be limited to the reviewed
implementation (Cloud Run, Artifact Registry, Secret Manager, Cloud Build only
if that build path is selected, and Container Scanning only if the owner accepts
its separate cost).
[`gcloud services enable`](https://docs.cloud.google.com/sdk/gcloud/reference/services/enable)

### Private R2 bucket and credentials

Open [Cloudflare R2 Overview](https://dash.cloudflare.com/?to=/:account/r2/overview)
before bucket or token input. R2 buckets are private by default. Public access
requires a separate `r2.dev` or custom-domain action and is outside this demo;
the wizard should verify that neither is enabled.
[Create R2 buckets](https://developers.cloudflare.com/r2/buckets/create-buckets/),
[R2 public buckets](https://developers.cloudflare.com/r2/buckets/public-buckets/)

The owner should create a Standard-class demonstration bucket and an **Object
Read & Write** token restricted to that bucket. Admin permissions are broader
than the application requires. R2 shows the Secret Access Key only when the
token is created, so collection must use hidden input and immediate placement
in a mode-0600 file or Secret Manager; it must never be redisplayed.
[R2 authentication and bucket-scoped permissions](https://developers.cloudflare.com/r2/api/tokens/),
[R2 S3 setup](https://developers.cloudflare.com/r2/get-started/s3/)

The S3-compatible endpoint is account-specific and uses region `auto` for a
normal bucket; jurisdictional buckets require the matching jurisdictional
endpoint. These are owner-confirmed configuration facts, not values a wizard
may guess.
[R2 authentication](https://developers.cloudflare.com/r2/api/tokens/),
[R2 Boto3 configuration](https://developers.cloudflare.com/r2/examples/aws/boto3/)

R2 charges for stored data and Class A/Class B operations. Its free allowance
applies only to Standard storage, usage is rounded to billing units, and other
metered services can still charge even though direct R2 egress is free. Bucket
creation therefore needs an explicit cost acknowledgement.
[R2 pricing](https://developers.cloudflare.com/r2/pricing/)

Rollback is intentionally two-step and destructive: revoke the application
token first, preserve or export required evidence, then empty and delete the
bucket only with a separate confirmation. R2 requires an empty bucket before
deletion and says emptied/deleted objects cannot be recovered. Never automate
that cleanup as a generic failure handler.
[Delete R2 buckets](https://developers.cloudflare.com/r2/buckets/delete-buckets/)

### Service identity and secrets

Open [IAM service accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
before identity creation and [Secret Manager](https://console.cloud.google.com/security/secret-manager)
before secret creation. Use a dedicated user-managed Cloud Run runtime identity
with no downloadable key. Google explicitly says not to set
`GOOGLE_APPLICATION_CREDENTIALS` on Cloud Run; the assigned service identity
should obtain Google credentials from the metadata server.
[Cloud Run service identity](https://docs.cloud.google.com/run/docs/securing/service-identity),
[create service accounts](https://docs.cloud.google.com/iam/docs/service-accounts-create)

The deployer and runtime identities are different trust roles. Google's
documented deployment roles are Cloud Run Developer on the service, Service
Account User on the selected service identity, and Artifact Registry Reader on
the specific image repository. The runtime identity needs Secret Manager
Secret Accessor only on the exact runtime secrets; it needs no runner, chain
signing, deploy, build, project Owner, or project Editor privilege.
[Cloud Run deployment roles](https://docs.cloud.google.com/run/docs/deploying),
[Cloud Run secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets)

For environment-variable secrets, Google recommends a numbered version rather
than `latest`; Cloud Run resolves the value when an instance starts and checks
the service identity's access during deployment. Secret payloads should be
accepted from hidden input/stdin or the Google console, never interpolated into
a displayed command. Evidence records only secret resource names and version
numbers, not values.
[Configure Cloud Run secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets),
[create and version secrets](https://docs.cloud.google.com/secret-manager/docs/creating-and-accessing-secrets)

### Immutable image, scan, and deploy

Open [Artifact Registry repositories](https://console.cloud.google.com/artifacts)
before repository creation and [Cloud Run services](https://console.cloud.google.com/run)
before deployment. Artifact Registry accepts image references by digest in the
form `LOCATION-docker.pkg.dev/PROJECT/REPOSITORY/IMAGE@sha256:...`; after push,
`gcloud artifacts docker images list ... --include-tags` reports the generated
digest. The wizard should build and test a uniquely tagged image, upload it only
after confirmation, record the resolved digest, and deploy only that reviewed
digest—not `latest` or another mutable tag.
[Artifact Registry image names](https://docs.cloud.google.com/artifact-registry/docs/docker/names),
[push images and inspect digests](https://docs.cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling),
[deploy images to Cloud Run](https://docs.cloud.google.com/run/docs/deploying)

If Cloud Build is selected, `gcloud builds submit` uploads source and initiates
a billable external build. It requires its own immediate confirmation. A local
Docker build plus an owner-confirmed push is a separate option and should not
silently fall back to Cloud Build.
[Build containers with Cloud Build](https://docs.cloud.google.com/build/docs/building/build-containers)

Container Scanning is optional, separately enabled, and paid. Enabling its API
can scan new supported images, while scan results still require owner review;
the wizard must not equate “scan completed” with vulnerability-free or safe.
[Artifact Analysis overview](https://docs.cloud.google.com/artifact-analysis/docs/container-scanning-overview),
[scanning cost controls](https://docs.cloud.google.com/artifact-analysis/docs/controlling-costs)

Deploy the API as a Cloud Run **service**, not a job or worker pool, using
request-based billing, minimum instances zero, the reviewed low maximum, the
dedicated runtime identity, numbered secret references, the immutable digest,
and `RUNNERS_ENABLED=false`. Cloud Run injects `PORT`; the ingress container
must listen on `0.0.0.0` at that port.
[Cloud Run container contract](https://cloud.google.com/run/docs/container-contract),
[request-based billing](https://docs.cloud.google.com/run/docs/configuring/billing-settings),
[minimum instances](https://docs.cloud.google.com/run/docs/configuring/min-instances),
[maximum instances](https://docs.cloud.google.com/run/docs/configuring/max-instances)

The FastAPI service must be publicly invokable for Vercel's ordinary external
rewrite and direct acceptance, but public invocation grants no application
authorization. `--allow-unauthenticated` or the equivalent console choice is a
security mutation requiring an explicit prompt. Nebula authentication remains
mandatory on protected routes.
[Allow public Cloud Run access](https://docs.cloud.google.com/run/docs/authenticating/public)

Direct acceptance should check the stable Cloud Run HTTPS URL: public `/live`
for process liveness, database-backed `/ready` for dependency readiness, and
protected routes for application-auth rejection. Cloud Run HTTP health-check
paths are externally reachable and obey the same exposure rules as other
service endpoints, so health responses must contain no sensitive details.
[Cloud Run health checks](https://docs.cloud.google.com/run/docs/configuring/healthchecks)

The private-object gate must demonstrate a bounded, non-production object
written/read across the Cloud Run API and laptop adapters and then cleaned up.
Do not expose the bucket or log presigned URLs: R2 defines them as bearer tokens
valid for one operation until expiry.
[R2 presigned URL security](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)

Before deployment, record the current revision/traffic state. Cloud Run
revisions are immutable; rollback routes 100 percent of traffic to the named
known-good revision. Traffic transitions are not instantaneous, so the wizard
must verify endpoints after rollback. Revision deletion is irreversible and is
not part of routine rollback.
[Cloud Run rollouts and rollback](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration),
[manage revisions](https://docs.cloud.google.com/run/docs/managing/revisions)

GCP-004 must then stop. It must neither invoke Vercel nor render/apply browser
routing and must say that direct backend acceptance is not browser acceptance.

## GCP-005: Vercel rewrite and browser cutover

Open the [Vercel dashboard](https://vercel.com/dashboard) and the selected
project before asking for approval. GCP-005 should first verify signed/sanitized
GCP-004 evidence and an actual `https://...run.app` origin. It must reject
placeholders, user-info URLs, paths/query fragments, HTTP, arbitrary hosts, and
any origin not equal to the accepted Cloud Run service origin.

Vercel external rewrites proxy the matching path without changing the browser
URL. A reviewed `/api/v1/:path*` rewrite to the exact accepted Cloud Run origin
therefore preserves Nebula's same-origin browser interface; it must not be
replaced with a direct cross-origin browser API URL. Vercel recommends testing
rewrites in a preview deployment before production.
[Vercel rewrites](https://vercel.com/docs/routing/rewrites)

The wizard should materialize the reviewed rewrite into a temporary deployment
artifact, validate it locally, create a preview deployment, and run non-secret
checks before a separate production confirmation. Every Vercel deployment has
a unique generated URL, allowing the candidate to be inspected without first
moving the production domain.
[Vercel deployments](https://vercel.com/docs/deployments/overview),
[generated deployment URLs](https://vercel.com/docs/deployments/generated-urls),
[`vercel inspect`](https://vercel.com/docs/cli/inspect)

Genuine browser acceptance remains an owner-observed test. The wizard can open
the real production frontend and guide challenge, verification, refresh,
logout, cookie-attribute inspection, and wrong/missing-Origin checks, but a
shell HTTP approximation cannot prove that access tokens remain only in module
memory or that the browser stores/sends the refresh cookie as designed. The
owner must explicitly attest to those observations; the evidence must redact
tokens, cookies, wallet signatures, and presigned URLs.

Before cutover, preserve the exact prior production deployment URL/routing
state. Vercel Instant Rollback can restore an eligible prior production
deployment; Hobby permits only the immediately previous production deployment,
while Pro/Enterprise permits other eligible deployments. A rollback disables
automatic production-domain assignment until explicitly undone. The wizard
must show this plan before changing production and verify restored routing and
authentication after rollback.
[Vercel Instant Rollback](https://vercel.com/docs/instant-rollback),
[`vercel rollback`](https://vercel.com/docs/cli/rollback)

No API, database, storage, wallet, or Cloud Run secret belongs in Vercel. If a
future server-side Vercel value is genuinely needed, sensitive variables are
write-only after creation, and changed variables apply only to new deployments.
[Vercel sensitive variables](https://vercel.com/docs/environment-variables/sensitive-environment-variables),
[Vercel environment behavior](https://vercel.com/docs/environment-variables)

## GCP-006: controlled laptop worker and runners

This wizard is local orchestration, not a cloud provisioning tool. It may open
the already accepted Cloud Run URL and vendor consoles for owner inspection,
run non-secret connectivity/configuration checks, and prepare existing reviewed
Nebula commands. It must not create or alter GCP, R2, Vercel, Supabase, DNS, or
contract resources.

The laptop's R2 access should use a separate bucket-scoped Object Read & Write
credential stored outside Git in a mode-0600 file. It must not reuse a Google
service-account key or expose the Cloud Run runtime's numbered secret values.
Where a single direct object operation suffices, a short-lived exact-object
presigned URL is narrower than sharing persistent S3 credentials; anyone who
obtains that URL can use it until expiry.
[R2 token permissions](https://developers.cloudflare.com/r2/api/tokens/),
[R2 presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)

Preflight should prove the API `/live` and database-backed `/ready` gates,
private R2 operation, RPC/chain and deployed-contract public identifiers, and
the repository's existing worker/provider/verifier custody separation without
printing credentials or private keys. These checks establish reachability and
configuration only; they do not authorize a process start.

Each worker or controlled runner start is a separate local side-effect with a
fresh immediate confirmation. The wizard should show a redacted command and
role, launch only the selected existing command, record its PID/status in a
private runtime directory, and expose an idempotent status/stop procedure. It
must never start all processes merely because `--check` or `--plan` succeeded.
It must verify again that the Cloud Run revision has `RUNNERS_ENABLED=false`.

The safe stop order and failure response are repository-defined operational
facts, not vendor behavior: stop locally launched runner/worker processes,
verify their recorded PIDs have exited, preserve sanitized evidence, and leave
Cloud Run API-only. Cloud Run's request-based lifecycle is not a substitute for
continuous Nebula runners because CPU allocation and billing differ outside
requests.
[Cloud Run billing and CPU allocation](https://docs.cloud.google.com/run/docs/configuring/billing-settings)

## What a wizard must not automate without the owner

- Account login, project selection/creation, billing association, budget mode,
  region or jurisdiction selection, legal/terms acceptance, and paid-feature
  selection.
- R2 bucket creation, token issuance/revocation, public-access changes, bucket
  emptying, or deletion without a stage-local confirmation.
- IAM role grants, service-account creation, secret creation/versioning, API
  enablement, image upload/scan, public Cloud Run access, or deployment without
  displaying a sanitized plan and obtaining immediate confirmation.
- Acceptance of vulnerability findings or cost exposure; those require human
  review rather than a boolean CLI exit status.
- Vercel production routing/deployment/rollback or browser-auth acceptance in
  GCP-004, or before GCP-004 evidence passes in GCP-005.
- Wallet approval, browser cookie/storage inspection, role-custody attestation,
  or the decision to start any worker/runner process.
- Destructive cleanup as an automatic response to a partial failure. Stop at
  the failure, report the last verified state, and offer the specific reviewed
  rollback only after a new confirmation.

## Evidence boundary

Wizard evidence may include public project ID, approved region, service name,
service URL, revision, image digest, bucket name, secret names and numeric
versions, resource identities, sanitized HTTP status/body assertions, timestamps,
and pass/fail decisions. It must exclude billing-account IDs, access/secret
keys, tokens, private keys, wallet signatures, database URLs, credential-bearing
RPC URLs, cookies, authorization headers, presigned URLs, secret payloads, and
raw environment/configuration files.

The existence of these sources or a passing local wizard test proves only the
wizard contract. It does not prove that an owner has deployed Cloud Run,
configured private R2 correctly, completed a Vercel cutover, exercised real
browser authentication, or run the controlled laptop worker/runners.
