# Owner-operated demo host runbook

## Purpose and status

This is a temporary, owner-operated demonstration route while OCI Always Free
capacity is unavailable. It is not a replacement for the OCI Phase 7 target,
does not change the PRD, and must not be represented as an unattended managed
production deployment.

The supported route is:

```text
Vercel Hobby frontend
  -> same-origin /api/v1/* rewrite
  -> https://<DuckDNS hostname>
  -> home router TCP 443/80
  -> always-on laptop Docker Caddy
  -> internal FastAPI :8000
  -> Supabase PostgreSQL / Arbitrum Sepolia
```

The frontend never calls the home backend directly. The Vercel rewrite is the
same browser-auth interface defined by [ADR 0001](../adr/0001-same-origin-browser-auth.md):
access tokens remain in browser memory and refresh cookies remain first-party
to the Vercel origin.

## Security and operating constraints

- Keep FastAPI port `8000` internal. Only Caddy publishes TCP `80` and `443`.
- Keep all five runner containers disabled. Starting transaction-signing
  runners is outside BE-002 and still requires its reviewed runtime ticket and
  secrets.
- Store database, JWT, and DuckDNS secrets only in
  `~/.config/nebula-owner-demo/` with owner-only permissions. Never commit or
  paste them into chat.
- Reserve the laptop's LAN address in the router, forward only TCP `80` and
  `443`, and ensure the router WAN address equals the detected public address.
  A mismatch normally means CGNAT/double NAT and blocks the DuckDNS route.
- A laptop, Docker engine, power, local Internet connection, router, DuckDNS
  updater, Supabase project, and Vercel project are all runtime dependencies.
  Put the machine on mains power and disable sleep during a demonstration.
- Cloudflare Quick Tunnels are intentionally excluded: their URLs are not a
  stable deployment origin. A named Cloudflare Tunnel requires a domain under
  the owner's Cloudflare account and needs a separate review before use.

## Run and verify

From the repository root, after this change is committed:

```bash
scripts/be002_owner_operated_demo_wizard.sh
```

The wizard performs these owner-gated stages:

1. verifies local Docker, source state, ports, frontend gates, and Chromium;
2. verifies or creates the stable Vercel Hobby origin;
3. configures DuckDNS, checks public-IP/DNS consistency, and guides router
   forwarding;
4. writes runtime-only Supabase/JWT/DuckDNS configuration outside Git;
5. runs Alembic and starts an isolated `nebula-owner-demo` Docker Compose
   project using the existing portable runtime definition;
6. configures persistent dynamic-DNS and laptop/Docker startup behavior; and
7. deploys the Vercel rewrite, runs real Chromium browser auth, and records
   public-only evidence.

The wizard must be run by the owner because it opens provider dashboards,
accepts secrets locally, changes router configuration, and performs external
deployments. It intentionally refuses uncommitted deployment-source changes.

## Switch profiles safely

The OCI profile remains untouched at `deploy/oci/` and the OCI wizard remains
`scripts/be002_production_auth_wizard.sh`.

To stop the temporary local profile:

```bash
docker compose --project-name nebula-owner-demo \
  --env-file "$HOME/.config/nebula-owner-demo/compose.env" \
  -f deploy/oci/compose.yaml down
```

Do not delete the local configuration directory until its secrets are no
longer needed. It is outside the repository and is not an OCI resource.

When OCI capacity becomes available, first stop this local profile. Then run
the existing OCI wizard. It independently deploys and verifies OCI HTTPS
before it asks to replace `frontend/vercel.json`; this prevents the frontend
from being switched to an unreachable OCI origin. The old local rewrite is
replaced only during that explicit final OCI step.

To switch back for a later demo, stop the OCI profile, ensure local router/DNS
are healthy, and rerun this owner-operated wizard. Each profile uses a distinct
Compose project name, so Docker volumes and running containers are not shared.

## Acceptance boundary

Successful `/live`, `/ready`, and deployed browser-auth checks prove the
temporary BE-002 browser route only. They do not make OCI complete, enable
runners, or close later worker, settlement, monitoring, load, or launch work.
