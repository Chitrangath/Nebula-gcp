# BE-002 Completion Report

**Final status:** `DONE` (2026-10-23)

## Hosted acceptance closure

GCP-005 completed the previously owner-controlled acceptance boundary. The
production frontend at `https://nebula-gcp.vercel.app` now preserves the
same-origin `/api/v1/*` interface and routes it to the accepted Cloud Run API.
The owner completed the genuine browser checks for wallet challenge and
verification, module-memory access-token handling, secure refresh-cookie
attributes and rotation, logout/revocation, and wrong/missing-Origin rejection.

Sanitized acceptance evidence is retained outside Git at
`~/.local/state/nebula-gcp/evidence/GCP005_BROWSER_CUTOVER.env`. A subsequent
read-only production check returned `200` for the frontend and the expected
backend `405` plus `Allow: POST` and `Cache-Control: no-store` for a GET to
`/api/v1/auth/challenge`, confirming that the Vercel rewrite reaches the
FastAPI authentication route without caching it. No token, cookie, signature,
private key, database URL, or presigned object URL is included in this report.

This closure supersedes the historical `PARTIAL` wording below, which records
the state and constraints at the end of the local implementation phase.

## Outcome

BE-002 locally establishes one coherent browser authentication topology.
Browser code calls the frontend origin at `/api/v1/*`; the development proxy
rewrites that prefix to backend `/v1/*`. The accepted decision is recorded in
`docs/adr/0001-same-origin-browser-auth.md`.

Refresh tokens are host-only cookies with `HttpOnly`, `Secure`,
`SameSite=Strict`, and `Path=/api/v1/auth`. Access tokens are retained only in
a module-private frontend variable and are not placed in cookies or browser
storage. Verify, refresh, and logout require an exact match to the configured
frontend `Origin`; credentialed CORS continues to allow only that configured
origin.

Authentication now uses configurable refresh-session expiry, row locks for
single-use challenges and refresh-session mutation, rotation on every refresh,
family revocation after reuse, and refresh-token-based logout revocation. The
logout bug that previously looked up a refresh-token digest in the access-token
column is corrected. SQLite-naive and PostgreSQL-aware persisted timestamps are
normalized before expiry comparisons.

Successful authentication responses and explicit authentication/security
rejections set `Cache-Control: no-store`. Framework-generated validation or
unexpected server errors contain no token material. The verification endpoint
now applies the same exact-Origin protection as refresh and logout, because it
is also a cookie-mutating browser operation.

## Public contract

- Browser URL: `/api/v1/auth/{challenge,verify,refresh,logout}`.
- Backend URL after proxy rewrite: `/v1/auth/{challenge,verify,refresh,logout}`.
- Verify, refresh, and logout require exact
  `Origin == FRONTEND_URL` equality.
- The deployment platform must provide the same `/api/v1/*` to `/v1/*`
  rewrite. Direct browser calls to a separate backend origin are unsupported.
- `FRONTEND_URL` must be the exact deployed browser origin, with no path.

## Completion boundary

The agent-executable implementation and local verification are complete. The
ticket remained `PARTIAL` at that time because its final acceptance boundary
crosses owner-controlled systems: creating/selecting a persistent PostgreSQL
database, provisioning one approved backend route and hostname, authenticating
to Vercel, installing the route's secrets, approving the deployments, and
exercising the cookie through the deployed browser origin. OCI remains the
canonical route; the temporary owner-operated route is available only while
OCI capacity is unavailable. An agent cannot truthfully manufacture that
external evidence or authorize those account changes.

The reviewed owner wizard at
`scripts/be002_production_auth_wizard.sh` performs all remaining setup and
verification without writing secrets to the repository. It has six necessary
stages: local toolchain and frontend gates; free Vercel origin; OCI Always Free
VM and free hostname; Supabase Free and server secrets; ARM64 backend
deployment/migration/HTTPS health verification; and the final Vercel rewrite
plus real-browser auth smoke. It installs locked frontend dependencies,
Chromium and its Linux libraries, and the Vercel CLI; verifies required WSL
tools; requires the selected 1-OCPU/6-GB OCI A1 control-plane profile and
refuses any OCI resource not visibly labelled `Always Free eligible`;
requires a zero-cost reserved public IPv4; independently verifies the VM's
ED25519 SSH host-key fingerprint before transmitting secrets; checks the Ubuntu
guest-firewall path for SSH, HTTP, and HTTPS; streams secrets over SSH to a
mode-0600 file outside the deployed release; and
writes only public closure evidence to
`docs/evidence/BE002_CLOSURE_EVIDENCE.md`.

If OCI capacity is temporarily unavailable, the separate
`scripts/be002_owner_operated_demo_wizard.sh` may instead be used for an
owner-operated demonstration host. It keeps the same browser-auth interface
and reuses the OCI Compose definition read-only under a distinct Docker Compose
project name, while keeping its own local secrets and DuckDNS configuration
outside Git. It does not change the OCI target or make BE-002 complete on its
own: the owner must still complete the public HTTPS and real-browser smoke.
The temporary route and its explicit switch-back procedure are documented in
`docs/runbooks/OWNER_OPERATED_DEMO_HOST.md`.

No placeholder backend origin is committed. The wizard creates
`frontend/vercel.json` only after the real OCI/Caddy HTTPS origin exists, orders the
external `/api/v1/:path*` rewrite before the SPA fallback, disables rewrite
caching on auth/API paths, and validates the deployed flow. After the wizard
passes and its evidence is reviewed, BE-002 can be changed to `DONE` and BE-003
can be unblocked.

Fly.io was removed after the owner clarified that every hosted service must
remain on a completely free tier. `deploy/oci/compose.yaml` keeps FastAPI
private behind Caddy, defines all five Phase 3 runner processes behind the
disabled-by-default `runners` profile, and preserves one shared storage volume.
BE-002 starts only `api` and `caddy`; activating transaction-signing runners
still requires the later reviewed runtime ticket and its secrets.

## Verification

The focused HTTP-interface suite covers challenge reuse and expiry, wallet
mismatch, access and refresh expiry, refresh rotation, replay-family
revocation, logout revocation, cookie creation/deletion attributes and path,
and allowed/disallowed Origin and CORS behavior. Replay-family revocation is
also exercised through a production-like request-scoped session that commits
successful responses and rolls back raised exceptions; this caught and fixed a
transaction-boundary bug that the shared test session had previously hidden.

- Focused BE-002 auth, health, and deployment suite: 24 passed.
- Complete default backend suite: 293 passed, 69 environment-gated tests
  skipped. The skipped tests include integration coverage that requires
  external PostgreSQL and Anvil services.
- Ruff check and format check passed for every changed Python file.
- The newly annotated auth and health router interfaces pass mypy body checking
  with external imports skipped and the resulting untyped FastAPI-decorator
  diagnostic disabled. The repository-wide strict mypy gate
  still reports 21 pre-existing errors from legacy SQLAlchemy `Column` model
  typing, Pydantic environment construction, and the missing python-jose stub;
  BE-002 does not conceal that baseline or expand into a model-layer migration.
- `git diff --check` passed.
- The persistent six-stage owner wizard passes `bash -n` and containerized
  ShellCheck (excluding only the template's unused color variable and
  intentional single-quoted literals); its library prefix is byte-identical to
  the repository wizard template, its embedded Vercel validator parses under
  Node 24, and its xtrace refusal was exercised without entering any credential
  or external-action stage.
- The locked production Docker image builds successfully for both local AMD64
  and the target OCI Ampere ARM64 architecture, runs as the non-root
  `app` user, returns 200 from `/live`, and returns a bounded 503 from `/ready`
  when PostgreSQL is deliberately unavailable.
- The OCI Compose model passes `docker compose config`; the pinned Caddy image
  accepts the TLS/reverse-proxy configuration; port 8000 is internal-only and
  the five runner services require the explicit `runners` profile.
- WSL-native Node 24.21.0 verification: 3/3 Vitest auth-client tests,
  TypeScript compilation, Vite 7.3.6 production build, and zero-warning ESLint
  all passed from `npm ci` and the generated lockfile.
- `npm audit --omit=dev --audit-level=high` and
  `npm audit --audit-level=high` passed with no high or critical findings.
  There are 2 production and 4 total moderate transitive findings in React
  Router 6 and Vitest 3. Their advertised remediations require breaking major
  upgrades, so they are explicitly deferred to the Phase 4 dependency
  integration rather than hidden behind `npm audit fix --force`. Unused
  RainbowKit and wagmi scaffold dependencies were removed; Phase 4 must select
  and integrate current wallet packages when wallet UI work actually begins.
- The Playwright deployed-origin test is implemented, statically included in
  the frontend lint pass, and successfully compiled/enumerated by Playwright.
  It opens the deployed page first and performs every auth request through
  in-page, frontend-relative `fetch`, relying on the browser's real Origin and
  cookie behavior rather than a manually injected header. Its live execution
  is deliberately pending because it requires the owner-authorized OCI/Vercel
  deployments; this is the sole remaining acceptance gate, not missing local
  implementation.

## Skill usage

### Discovered

`solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`,
`diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`,
`improve-codebase-architecture`, `handoff`, `ask-matt`,
`setup-matt-pocock-skills`, `teach`, and `wizard`.

### Applied

1. `tdd`: browser-auth behavior was driven through red-green HTTP-interface
   tests, including the cookie-path and logout-revocation defects.
2. `domain-modeling`: the browser, proxy, backend, access-token, refresh-token,
   and session boundaries were made explicit in an accepted ADR.
3. `codebase-design`: the design keeps browser routing and token ownership
   behind narrow, stable seams instead of exposing deployment hosts to clients.
4. `wizard`: the owner-only Node/provider/database/deployment/browser procedure
   is encoded as a gated, secret-safe script rather than informal instructions.
5. `research`: current Node, OCI Always Free, Supabase Free, Vercel Hobby, and
   rejected-host behavior was verified from primary sources in
   `docs/research/BE002_PRODUCTION_BROWSER_AUTH_SOURCES.md` and
   `docs/research/BE002_ZERO_COST_HOSTING_OPTIONS.md`.
6. `code-review`: the complete working-tree diff receives independent standards
   and BE-002 conformance reviews before handoff.

### Temporary owner-operated contingency addition

1. `tdd`: a red deployment-profile contract test now asserts the separate
   project name, disabled runners, secret-file permissions, DuckDNS/CGNAT
   checks, Vercel rewrite, and explicit OCI switch-back.
2. `domain-modeling`: the temporary route is explicitly named an
   **owner-operated demo host**, rather than a production deployment or an OCI
   replacement.
3. `codebase-design`: the portable Docker runtime remains behind the same
   narrow Compose interface; the laptop path is an adapter with its own project
   name and runtime configuration, not a fork of OCI configuration.
4. `wizard`: a separate seven-stage, repeatable human procedure now handles
   local Docker, Vercel, DuckDNS/router checks, local secrets, public TLS,
   persistence, browser smoke, and evidence without modifying OCI files.
5. `code-review`: the formal independent review cannot run because this
   repository does not contain the skill-required `docs/agents/issue-tracker.md`;
   syntax, ShellCheck, Compose normalization, focused tests, and a manual
   security/spec review were run instead.

### Not applied

`diagnosing-bugs` was unnecessary because failures were isolated by the TDD
loop. Smart-contract security, routing, teaching, handoff, and broad
refactoring skills are outside this browser-auth ticket. The repository's Matt
Pocock `tdd`, `codebase-design`, and `code-review` skills were applied to the
TypeScript slice. `PARTIAL` describes only the unexecuted owner-controlled
deployment/browser gate; all locally executable implementation and verification
work is complete.
