# GCP Demo Deployment Threat Model

**Status:** GCP-003 local storage/runtime closure; remote-provider evidence and
all cloud or Vercel mutations remain owner-gated

**Reviewed:** 2026-10-16

**Scope:** the temporary GCP demo hosting adapter from the Vercel rewrite to
the public Cloud Run FastAPI API, its runtime identity and secrets, cost
controls, acceptance, rollback, and OCI switch-back

## Security objective and hard boundary

The GCP profile may expose the existing FastAPI request interface through a
stable Cloud Run HTTPS origin. It must not create a second application or
change Nebula's protocol, PostgreSQL schema, Arbitrum Sepolia deployment,
worker protocol, proof envelope, verifier, verdict, settlement, or browser-auth
interface.

Cloud Run hosts the API container only. `RUNNERS_ENABLED=false`, one `api`
container, request-based billing, and zero minimum instances are deployment
invariants. The deterministic fixture worker and the receipt, assignment,
settlement, event, and reconciliation runners execute only on the owner laptop
during supervised testing or faculty demonstrations. The Cloud Run runtime
identity receives no blockchain transaction-signing key.

## Assets, actors, and trust seams

| Asset or actor | Trust assumption | Failure impact | Required control |
|---|---|---|---|
| AI user browser | Uses the Vercel origin | Token or cookie exposure, forged cross-origin request | Preserve same-origin `/api/v1/*`, memory-only access token, host-only secure refresh cookie, exact Origin checks |
| Vercel rewrite | Forwards the unchanged browser path to the reviewed origin | Hostname substitution, caching user responses, bypass of browser-auth assumptions | Materialize only after exact HTTPS origin approval; API rule first; caching disabled; browser smoke before cutover |
| Public Cloud Run API | Accepts internet traffic | Abuse, denial of wallet/API flows, quota and billing consumption | Low max instances, application rate limits, bounded request timeout, logs/alerts, no runner work |
| Runtime service identity | Fetches only runtime secrets | Project compromise if over-privileged | Dedicated user-managed identity; secret accessor on exact secrets only; no deploy/build/admin role or key file |
| Secret Manager | Supplies the reviewed runtime secret set | Database/storage/session compromise | Numbered versions, no literal values, least privilege, revision-based rotation and rollback |
| Supabase PostgreSQL | Authoritative workflow/lease state | Availability loss or data exposure | TLS credential URL in Secret Manager; `/ready` fails closed; no credentials in logs/evidence |
| Arbitrum Sepolia | Existing testnet contract network | Stale or failed reads; transaction risk if a runner were misplaced | API has no signer; owner laptop runners retain the established controlled transaction path |
| Owner/deployer | Approves billable and externally visible changes | Wrong project, region, identity, image, storage, or origin | Thirteen explicit gates, preview of public values, stop before every mutation |
| Private durable object store | Shares accepted input, model, result, and proof objects across runtimes | Disclosure, overwrite, orphaning, or demo failure | Private bucket; bucket-scoped token; validated keys; conditional immutable writes; compensating cleanup |
| Artifact/build path | Produces immutable container input | Supply-chain substitution or unexpected build/registry charges | Review Dockerfile and scan result; deploy only a recorded digest; separate build identity if Cloud Build is used |

## Threat analysis and controls

### Public Cloud Run ingress

The Vercel external rewrite cannot mint a Google identity token, so the demo
API requires public HTTP invocation. Public invocation grants no Secret
Manager or project privilege, but every endpoint becomes reachable at the
`run.app` origin. Application authentication remains mandatory on protected
routes, direct browser use of `run.app` is unsupported, and `/live` and
`/ready` are the deliberately unauthenticated health interfaces. The owner must review whether
public access is implemented through the current recommended IAM-check setting
or `allUsers` invoker binding immediately before deployment.

Google documents public Cloud Run access and ingress separately in
[Allowing public access](https://cloud.google.com/run/docs/authenticating/public)
and [Restrict network ingress](https://cloud.google.com/run/docs/securing/ingress).

### Vercel rewrite and hostname trust

An attacker or operator typo could route authenticated browser traffic to an
attacker-controlled origin. The tracked rewrite contains an unmistakable
placeholder and the validator accepts only an HTTPS origin without credentials,
path, query, or fragment. A later cutover ticket must substitute the exact observed Cloud Run
service origin only after `/live` and database-backed `/ready` pass. The
browser-visible URL remains Vercel `/api/v1/*`; no access token is placed in
storage and no cross-site refresh-cookie design is introduced.

Vercel documents that an external rewrite changes the upstream without
changing the browser URL. For new projects, Vercel's CDN can honor cache
headers from external origins by default; Nebula therefore requires the
explicit `x-vercel-enable-rewrite-caching: 0` opt-out and verifies `no-store`
behavior for authenticated API traffic. See
[Rewrites](https://vercel.com/docs/routing/rewrites) and the dated
[external-origin cache change](https://vercel.com/changelog/vercels-cdn-now-respects-cache-control-headers-from-external-origins-by-default).

### Least-privilege service identity

Bootstrap/owner, deployer, optional builder, and runtime are distinct roles.
The deployer may update only the named Cloud Run service, read the selected
Artifact Registry repository, and act as only the runtime service identity.
The runtime identity receives only `roles/secretmanager.secretAccessor` on the
exact required runtime secrets. It receives no project Editor/Owner, deployment, build,
registry-write, service-account-key, database-admin, or chain-signing access.

Google describes the service identity as the principal used by the running
container and requires the deployer to have Service Account User on that
identity in [Configure service identity](https://cloud.google.com/run/docs/securing/service-identity).
The documented deployment-role baseline is Cloud Run Developer, Artifact
Registry Reader, and Service Account User in
[Deploying container images](https://cloud.google.com/run/docs/deploying).

### Secret Manager delivery and rotation

The GCP-003 service contract references every required secret and public
runtime value through validated placeholders. Before deployment, the owner
must still materialize and review this inventory:

| Classification | Settings | Required treatment |
|---|---|---|
| Always secret | `DATABASE_URL`, `JWT_SECRET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | Exact Secret Manager secret, owner-approved numbered version |
| Secret when credential-bearing | `ARBITRUM_SEPOLIA_RPC`, `ARBITRUM_SEPOLIA_WS`, `R2_PUBLIC_URL` | Secret Manager if it contains credentials or signed query data; otherwise reviewed non-secret origin |
| Public deployment configuration | `CHAIN_ID`, `USDC_SEPOLIA_ADDRESS`, `NEBULA_PAYMENT_CONTRACT`, `R2_ACCOUNT_ID`, `R2_BUCKET_NAME`, confirmation/finality bounds | Explicit owner-approved placeholder; validate against existing deployment facts |
| Forbidden in Cloud Run | `BACKEND_PRIVATE_KEY`, worker signer/private key, provider wallet key, service-account key, every runner-enable setting | Must be absent |
| Excluded optional feature | `PINATA_API_KEY`, `PINATA_API_SECRET` | Omit; IPFS publication is not part of the GCP demo profile |

Every Secret Manager reference uses an owner-approved numeric version, never
`latest`. Secret values must not appear in shell arguments, Git, image layers,
build arguments, Vercel configuration, screenshots, logs, or evidence.
Rotation creates a new version and a new Cloud Run revision; traffic moves only
after acceptance, and the previous version remains enabled through the
rollback window.

Google recommends Secret Manager for Cloud Run and numbered versions for
environment-variable secrets because they are resolved at instance startup in
[Configure secrets](https://cloud.google.com/run/docs/configuring/services/secrets).

### Public traffic abuse

Unauthenticated health requests and hostile traffic can consume concurrency,
database connections, log volume, egress, and billable request time. Controls
are `maxScale=2`, concurrency 8, timeout 60 seconds, bounded health responses,
existing application authentication/rate limits, request-based billing, and
owner monitoring during demo windows. Maximum instances limits capacity, not
money. No keep-alive traffic is used to simulate continuous runners. A load
balancer, Cloud Armor, API Gateway, global rate-limit store, or denial-of-
service guarantee is not part of this demo profile.

### Logs, egress, build, and registry cost exposure

Cloud Run compute/requests, internet egress, Cloud Logging ingestion or
retention, Artifact Registry storage, vulnerability scanning, Cloud Build,
Secret Manager access, Supabase limits, taxes, and currency conversion can
cost money. Build logs and application logs can also leak origins, identifiers,
payload metadata, or exception details. The owner reviews pricing, creates
budget alerts, considers an eligible spend cap, sets retention consciously,
and validates that no secret-bearing values are logged. Alerts-only budgets do
not cap charges; spend-cap enforcement can lag and can pause eligible services.

Primary sources: [Cloud Run pricing](https://cloud.google.com/run/pricing),
[Cloud Billing budgets](https://cloud.google.com/billing/docs/how-to/budgets),
and [spend cap budgets](https://cloud.google.com/billing/docs/how-to/budgets-spend-caps).

### Request lifecycle and runner escape

Request-based Cloud Run allocates CPU around request processing and a service
with minimum instances zero can scale to zero. Background loops cannot rely on
incidental traffic or a warm instance. The template and validator prohibit
runner-named configuration and runner commands in addition to requiring
`RUNNERS_ENABLED=false`. Enabling instance-based billing, minimum instances,
Cloud Run Jobs, scheduled triggers, worker pools, or a tick interface is a
different architecture and requires a new ticket.

See [Cloud Run billing settings](https://cloud.google.com/run/docs/configuring/billing-settings)
and [minimum instances](https://cloud.google.com/run/docs/configuring/min-instances).

## Durable object-storage boundary

GCP-003 closes the local adapter gap at the existing `StorageBackend` seam.
`FileStorage` remains the local/test adapter; the deployed template requires
the S3-compatible durable adapter, private R2 bucket, explicit namespace, and
Secret Manager references for object credentials. API and controlled laptop
runners construct the same adapter contract. Browser and worker protocols do
not change.

All keys pass one bounded relative-POSIX validator. Immutable writes use an
atomic `If-None-Match: *` request and accept only an exact-byte retry. Requests
never add a public ACL. Direct capabilities, if a future path needs one, are
limited to one operation, one exact key, and at most 300 seconds; current
browser and worker reads remain backend mediated. PostgreSQL and object-store
writes are not one transaction, so request flows retain compensating deletion.

Fake-client tests prove local request construction, private posture, key
rejection, conditional writes, cleanup behavior, and independently built
adapters sharing one backing store. They do **not** prove that an R2 bucket
exists, credentials are correctly scoped, the endpoint interoperates, or real
Cloud Run and laptop processes exchange objects. Those remain GCP-004 gates.

## Deployment and acceptance gates

No deployment or traffic cutover is allowed until the owner has approved the
project, region, billing exposure, budgets, APIs, private bucket, bucket-scoped
object token, IAM bindings, secret names/versions, immutable image digest, and
exact service configuration. Cloud Run acceptance
requires public `/live` `200`, database-backed `/ready` `200`, a bounded
unavailable-database `/ready` `503`, and confirmation that the deployed
revision still has zero minimum instances and no runner or signing-key input.
Before Vercel cutover, a non-production object must pass Cloud Run write/laptop
read and laptop write/Cloud Run read/delete acceptance.
Vercel acceptance then requires allowed/wrong/missing Origin checks and a real
browser verify/refresh/logout smoke with the unchanged cookie attributes.

## Rollback

Rollback is deliberately two-layered:

1. Stop the laptop worker and all five controlled runners.
2. Route Cloud Run traffic to the recorded last-known-good immutable revision
   and repeat health/auth checks. Google supports revision traffic changes and
   rollback in [Rollbacks, gradual rollouts, and traffic migration](https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration).
3. If the GCP upstream is still unacceptable, restore the immediately previous
   known-good Vercel production deployment. Vercel documents plan-dependent
   rollback eligibility in [Instant Rollback](https://vercel.com/docs/instant-rollback).
4. Preserve sanitized evidence before any separately approved resource
   shutdown or deletion.

## OCI switch-back

OCI remains canonical in the original repository. Switch-back verifies the
original OCI HTTPS origin independently, confirms its exact Origin/CORS/cookie
configuration, obtains approval for the exact rewrite change, routes Vercel
`/api/v1/*` back to OCI, and repeats real-browser authentication acceptance.
Only after the observation window may the owner separately authorize stopping
or removing GCP resources. No OCI file is restored or recreated in this copy.

## Residual risks and non-claims

- Budget alerts can arrive after usage and are not a guaranteed cost ceiling.
- `maxScale=2` cannot prevent all abuse or all charges.
- A public `run.app` endpoint remains directly reachable even though supported
  browser traffic uses Vercel.
- A single region, Supabase availability, third-party egress, and cold starts
  can interrupt demonstrations.
- GCP-002 proves no cloud-side policy, deployment, public reachability,
  database-backed readiness, Vercel cutover, or browser acceptance.
- The profile makes no continuous hosted runner, real GPU proof, fully hosted
  end-to-end, production SLA, or production-readiness claim.

## Owner-wizard controls and residual local risk

The three owner wizards create a new privileged local seam. They refuse shell
tracing and non-interactive execution, store each sensitive value outside Git
in a mode-0600 file under a mode-0700 directory, and never print secret values
or full secret-bearing commands. Every cloud, billing, IAM, secret, upload,
deployment, Vercel, rollback, or process-start action has an immediately prior
typed confirmation. `--check`, `--plan`, `--help`, and GCP-005 evidence
validation perform no external mutation.

Protected local files are still long-lived credentials: compromise of the
owner account, backup, swap, shell history, process environment, or laptop can
expose them. The owner must use an encrypted device, restrict local account
access, stop processes after demonstrations, rotate credentials after suspected
exposure, and remove protected state only through a separately reviewed
cleanup decision.

Sanitized evidence is a gate, not an attestation. GCP-005 validates its shape
and security posture but cannot prove the observations were genuine; the owner
must review the referenced origin, digest, commit, and hashes. Temporary Vercel
staging copies can become stale or retain build output, so they live outside
Git and must be removed after acceptance or rollback. PID files can become
stale; the stop procedure validates numeric recorded PIDs and signals only
those processes, but the owner must review status and logs before retrying.
