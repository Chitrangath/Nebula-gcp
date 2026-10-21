# GCP-005 Vercel and Browser Cutover

Status: later owner-executed procedure; blocked until valid GCP-004 sanitized
direct-acceptance evidence exists.

```bash
scripts/gcp005_vercel_browser_cutover_wizard.sh --check
scripts/gcp005_vercel_browser_cutover_wizard.sh --plan
scripts/gcp005_vercel_browser_cutover_wizard.sh --validate-evidence
scripts/gcp005_vercel_browser_cutover_wizard.sh --run
```

The wizard validates the real Cloud Run HTTPS origin and the exact production
frontend origin, then renders `deploy/gcp-demo/vercel-rewrite.template.json`
outside Git. The shared validator must accept both the already materialized
Cloud Run service and rewrite before a Vercel mutation is offered.

Deployment occurs from an isolated temporary copy of `frontend/` containing
the rendered `vercel.json`; the repository never receives a guessed or
placeholder Cloud Run origin. Record the current known-good production
deployment before approving cutover.

Browser acceptance must use a genuine browser and cover challenge, wallet
verify, access token held only in frontend module memory, the host-only refresh
cookie (`HttpOnly`, `Secure`, `SameSite=Strict`, path `/api/v1/auth`), refresh
rotation, logout/revocation, and rejection of wrong or missing Origin. The
browser continues to call Vercel `/api/v1/*`; a direct cross-origin Cloud Run
browser design is forbidden.

If any check fails, do not accept the cutover. Use the final rollback gate to
restore the recorded prior Vercel production deployment, then repeat browser
authentication acceptance. Delete the temporary frontend copy after acceptance
or rollback.
