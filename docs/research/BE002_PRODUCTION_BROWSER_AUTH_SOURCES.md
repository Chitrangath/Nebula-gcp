# BE-002 Production Browser-Auth Deployment Sources

Retrieved: 2026-09-26 (UTC)

Scope: primary-source facts required to close BE-002 safely. This note does
not authorize deployment, account creation, secret entry, or changes to an
external service.

## Current repository facts

- Browser code uses the frontend-relative `/api/v1/*` API surface. The local
  Vite proxy rewrites it to the backend's `/v1/*` routes.
- The backend permits exactly `FRONTEND_URL` as a credentialed CORS origin and
  requires that same exact `Origin` for verify, refresh, and logout.
- Refresh cookies are `HttpOnly`, `Secure`, `SameSite=Strict`, and scoped to
  `/api/v1/auth`.
- The closure implementation adds a reviewed `backend/Dockerfile` and OCI
  Compose/Caddy artifacts under `deploy/oci/`. The persistent owner wizard at
  `scripts/be002_production_auth_wizard.sh` creates `frontend/vercel.json` only
  after the real OCI/Caddy HTTPS origin is known, so no placeholder destination is
  committed.

## Required production topology

The deployed browser must request the public frontend URL, not OCI directly:

```text
https://<frontend-origin>/api/v1/<path>
  -> Vercel external rewrite
  -> https://<backend-origin>/v1/<path>
```

Vercel documents that an external rewrite forwards to an external origin while
keeping the browser URL unchanged. This supports the chosen same-origin
cookie design: the browser interacts with the frontend origin, and the
backend receives the original frontend `Origin` header. The cookie outcome is
an implementation inference from that documented URL-preserving reverse proxy
behavior and must be validated with the production browser smoke test below.

Source: [Vercel: Rewrites to external origins](https://vercel.com/docs/routing/rewrites).

The explicit, fixed-destination rewrite must be:

```json
{
  "source": "/api/v1/:path*",
  "destination": "https://<approved-backend-origin>/v1/:path*"
}
```

Do not make the destination client-controlled, configurable from browser
input, or a wildcard host. Vercel calls out that rewrite configurations can
create security problems, so the destination must remain an exact approved
HTTPS origin.

## One additional required security gate: disable API edge caching

This is the only extra gate beyond the four previously proposed wizard
stages. Vercel now honors upstream cache-control headers for external rewrites
by default for new projects created on or after 2026-04-06. Authentication,
session rotation, and user-specific API results must never be cached at the
Vercel edge. The production configuration must therefore include:

```json
{
  "headers": [
    {
      "source": "/api/v1/:path*",
      "headers": [
        { "key": "x-vercel-enable-rewrite-caching", "value": "0" }
      ]
    }
  ]
}
```

This is Vercel's documented opt-out. It applies to all Nebula API responses;
do not add API caching as part of BE-002.

Sources: [Vercel: disabling external-rewrite caching](https://vercel.com/docs/routing/rewrites#disabling-caching-for-rewrites-to-external-origins) and [Vercel CDN caching change](https://vercel.com/changelog/vercels-cdn-now-respects-cache-control-headers-from-external-origins-by-default).

## SPA routing interaction

Vercel says a Vite SPA needs a catch-all rewrite to `/index.html` for deep
links. Rewrites are evaluated in configured order, so the specific API rewrite
must appear before the SPA catch-all:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "rewrites": [
    {
      "source": "/api/v1/:path*",
      "destination": "https://<approved-backend-origin>/v1/:path*"
    },
    { "source": "/(.*)", "destination": "/index.html" }
  ],
  "headers": [
    {
      "source": "/api/v1/:path*",
      "headers": [
        { "key": "x-vercel-enable-rewrite-caching", "value": "0" }
      ]
    }
  ]
}
```

The `vercel.json` belongs in the deployed frontend project root. If Vercel is
configured with `frontend/` as its Root Directory, that means
`frontend/vercel.json` in this repository. If the Vercel project instead uses
the repository root, it must be placed at the repository root and have the
correct frontend build/output configuration. Decide this once and do not
maintain conflicting files.

Sources: [Vercel: Vite SPA deep links](https://vercel.com/docs/frameworks/frontend/vite#using-vite-to-make-spas) and [Vercel: rewrite configuration](https://vercel.com/docs/routing/rewrites).

## Human wizard stages and exact gates

### 1. Working Node toolchain and frontend verification

The current environment cannot run the frontend build because `npm` resolves
to the Windows installation under `/mnt/c/Program Files/nodejs/` and refuses
the WSL invocation. The current Linux shell reports WSL 2, so this is a PATH
mixing problem, not proof that the Linux environment itself is unsupported.

Install a current Node LTS **inside the WSL distribution** (Node 20 reached
end of life on 2026-03-24; Node advises production applications to use Active
or Maintenance LTS releases). Node's download page documents the Linux nvm
workflow, including `nvm install 24` and version checks. The nvm installer
itself is third-party, so the operator should use its current upstream
installation command only after reviewing it.

Before installing dependencies, these must show WSL-local paths rather than
`/mnt/c/...`:

```bash
command -v node
command -v npm
node --version
npm --version
```

Use Node 24 LTS (or a later supported LTS). The closure implementation adds an
npm lockfile and does not use a Corepack-managed package manager, so Corepack
is not a prerequisite. From `frontend/`, run `npm ci`, review the lockfile
before committing it, and then run:

```bash
npm run build
npm run lint
npm audit --omit=dev --audit-level=high
npm audit --audit-level=high
```

Record `node --version`, `npm --version`, and both command results. Do not
commit `node_modules/`.

Sources: [Node.js release schedule](https://nodejs.org/en/about/previous-releases),
[Node.js downloads](https://nodejs.org/en/download/current), and [Node.js npm
introduction](https://nodejs.org/learn/getting-started/an-introduction-to-the-npm-package-manager).

### 2. Deploy the backend on OCI Always Free only after artifacts are reviewed

The agent must first verify the locked production Dockerfile for the target
Ampere ARM64 architecture and the Compose/Caddy interface under `deploy/oci/`.
FastAPI binds to `0.0.0.0:8000` only on the private Compose network; Caddy alone
publishes ports 80 and 443 and obtains the public TLS certificate. Neither the
image nor the committed Compose definition contains an environment file.

The operator must then:

1. Keep the OCI tenancy on Free Tier and create only a VM whose console labels
   the selected shape and allocation `Always Free eligible`. Do not click
   Upgrade.
2. Provision the Supabase Free PostgreSQL database and run Alembic migrations
   through the reviewed release process before serving traffic. The backend
   cannot authenticate users without its schema and `DATABASE_URL`.
3. Stream only the scoped values over SSH into `/opt/nebula/config/backend.env`
   with mode 0600. Use examples only as name checklists; do **not** upload a
   local `.env` wholesale. `JWT_SECRET`, `DATABASE_URL`, RPC credentials, R2
   credentials, and the verifier private key remain out of Git and images.
4. Set `FRONTEND_URL` to the exact final HTTPS Vercel origin, including scheme
   and no path. It must be the same origin users will browse.
5. Point the free hostname to the OCI public IP, start Caddy, and capture the
   resulting stable `https://<backend-origin>` URL.
6. Verify `GET https://<backend-origin>/live` and `/ready`, then inspect Docker
   Compose logs for startup, certificate, or migration errors. `/ready`
   executes a database probe; `/live` intentionally does not.

Oracle documents that Always Free resources are limited to the tenancy home
region and may reclaim idle compute. Caddy documents automatic HTTPS when a
public hostname resolves to the server and ports 80/443 are reachable.

Sources: [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), [Oracle Free Tier signup](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signingup_topic-Sign_Up_for_Free_Oracle_Cloud_Promotion.htm), and [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).

### 3. Configure and deploy Vercel with the fixed rewrite

The operator must link the intended Vercel project to the repository/frontend
root, preserve the reviewed `vercel.json`, and deploy it. The rewrite's
destination must use the stable backend HTTPS origin obtained in stage 2;
never use a temporary local address or a raw secret-bearing URL.

Set the frontend's Node version to the one successfully verified in stage 1
if the project requires an explicit Vercel Node version. Re-run the production
deployment after adding the rewrite, its anti-caching header, and the SPA
fallback.

Do not rely on a Vercel preview URL for the auth smoke unless the backend is
temporarily and deliberately configured to allow that exact preview origin.
The backend's security model intentionally allows one exact `FRONTEND_URL`,
so a generated preview hostname will not pass its CORS/origin checks. Run the
actual auth smoke against the stable production frontend origin, or configure
a dedicated stable staging origin through an equally strict deployment.

Vercel recommends preview deployments for rewrite testing, but Nebula's
single-exact-origin policy requires the additional configuration described
above if a preview is used.

Sources: [Vercel: testing rewrites](https://vercel.com/docs/routing/rewrites#testing-rewrites) and [Vercel project configuration](https://vercel.com/docs/project-configuration).

### 4. Real browser auth smoke and evidence capture

Using the stable frontend HTTPS origin in a real browser with a wallet:

1. Request and sign the wallet challenge.
2. Complete verification.
3. Inspect DevTools/Application storage: the refresh cookie is present for the
   frontend host only; it is `HttpOnly`, `Secure`, `SameSite=Strict`, and its
   path is `/api/v1/auth`.
4. Confirm no access token is stored in localStorage or sessionStorage.
5. Refresh the access token by calling the frontend-relative
   `/api/v1/auth/refresh` path. Confirm a new refresh cookie replaces the old
   one.
6. Replay the prior refresh cookie only in a controlled non-production test
   session, if available; it must be rejected and invalidate its family. Do
   not extract, log, or share a real user token.
7. Log out via `/api/v1/auth/logout`, then confirm the cookie is cleared and a
   further refresh is rejected.
8. Confirm browser Network entries retain the frontend `/api/v1/...` URL,
   never redirect to OCI, and return no `Access-Control-Allow-Origin: *`.

Capture only status codes, response headers with cookie **values redacted**,
and screenshots that contain no secrets. This provides the evidence to mark
BE-002 done.

## Do not combine this closure with unrelated deployment work

BE-002 only needs a minimal, secure production deployment sufficient to prove
the browser authentication topology. It does not authorize contract changes,
Arbitrum deployments, frontend feature work, worker GPU execution, a public
launch, or broader Phase 7 infrastructure. Those remain separate tickets.
