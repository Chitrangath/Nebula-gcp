# GCP-004 Foundation and Direct Backend Acceptance

Status: owner-executed procedure; not executed by the GCP-004 wizard-design ticket.

Run only from the reviewed clean `feat/gcp-demo-host` branch:

```bash
scripts/gcp004_foundation_deploy_wizard.sh --check
scripts/gcp004_foundation_deploy_wizard.sh --plan
scripts/gcp004_foundation_deploy_wizard.sh --bootstrap
scripts/gcp004_foundation_deploy_wizard.sh --run
```

Use `--bootstrap` only from an interactive Ubuntu/WSL terminal. It detects an
existing Google Cloud CLI or, after an exact owner confirmation, installs it
from Google's signed apt repository. It then separately asks before starting
`gcloud auth login --no-launch-browser`, avoiding an unreliable browser callback
into WSL, and repeats the non-mutating local check. Bootstrap does not
select a project, enable an API, create a resource, or run the deployment.

`--bootstrap` and `--run` require an interactive terminal. `--run` opens official documentation and
dashboard pages before capturing values, stops for an exact typed confirmation
before every external or billable action, and refuses a dirty source tree,
placeholder configuration, mutable image reference, `FileStorage`, enabled
Cloud Run runners, public R2 access, or incomplete runtime configuration.

Protected values are stored as individual mode-0600 files under
`${XDG_CONFIG_HOME:-$HOME/.config}/nebula-gcp`. Sanitized evidence is stored
under `${XDG_STATE_HOME:-$HOME/.local/state}/nebula-gcp/evidence`. Neither path
is inside Git. Never enable shell tracing, paste secrets into command-line
arguments, or copy secret-bearing commands into evidence.

The thirteen stages cover clean source, project/region/billing and cost risk,
budgets, API enablement, private R2 bucket, bucket-scoped Object Read & Write
token, runtime identity/IAM, numbered secrets, immutable image, API-only Cloud
Run deployment, direct `/live` and database-backed `/ready`, and one
non-production fixture flow proving private input/model/result exchange between
Cloud Run and the laptop Worker.

The health gate also renders and deploys a separate temporary Cloud Run probe
service from the same immutable image. The probe receives no production
traffic, starts on `/live`, uses an intentionally unreachable dummy database
URL, and must return `/live = 200` and `/ready = 503`. The owner separately
confirms its creation, temporary public invocation, and deletion. The probe
does not alter the production service or Supabase configuration.

Direct storage acceptance executes two bounded non-production fixture jobs
through the existing public user and authenticated Worker interfaces. The
wizard captures separate AI-user, GPU-provider, Worker-signer, and deployed
Verifier keys as protected mode-0600 configuration values, validates the role
separation, provisions the fixture model in private R2, and runs the five
laptop coordinators plus the fixture Worker only for the duration of the
probe. The probe always terminates its child processes. The AI-user wallet
must hold test ETH and test USDC; the provider and Verifier wallets require
test ETH.

The probe verifies Cloud Run input upload, laptop retrieval of the input and
model through Cloud Run, result upload into private R2, authorized result
download through Cloud Run, proof settlement, and database/chain
reconciliation. It records accepted-input and downloaded-result SHA-256
values plus public testnet identifiers, never object bytes, credentials,
cookies, access tokens, or presigned capability URLs. This does not establish
production readiness or real GPU proof.

The wizard stops after writing `GCP004_DIRECT_ACCEPTANCE.env`. It contains the
accepted origin, immutable digest, source commit, API-only/storage posture, and
sanitized hashes. It does not modify Vercel, DNS, frontend routing, or browser
authentication.

Rollback before cutover:

1. Stop every laptop Worker/runner process.
2. Route Cloud Run traffic to the recorded prior revision or remove traffic
   from the failed candidate.
3. Re-run direct `/live` and `/ready` checks.
4. Preserve sanitized evidence and do not delete resources without separate
   approval.

Cloud Run, Artifact Registry, logging, Secret Manager, egress, Cloud Build (if
chosen), R2, and Supabase may generate charges. Budget alerts are not hard cost
caps.
