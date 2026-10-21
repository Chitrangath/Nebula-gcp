# GCP-004 Foundation and Direct Backend Acceptance

Status: owner-executed procedure; not executed by the GCP-004 wizard-design ticket.

Run only from the reviewed clean `feat/gcp-demo-host` branch:

```bash
scripts/gcp004_foundation_deploy_wizard.sh --check
scripts/gcp004_foundation_deploy_wizard.sh --plan
scripts/gcp004_foundation_deploy_wizard.sh --run
```

`--run` requires an interactive terminal. It opens official documentation and
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

Direct storage acceptance uses only the existing authenticated worker
interface. It records accepted-input and result SHA-256 values, never object
bytes, credentials, cookies, access tokens, or presigned capability URLs. This
does not establish production readiness or real GPU proof.

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
