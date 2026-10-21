# GCP-001 Local API-Only Adapter Contract Completion Report

## Outcome

GCP-001 establishes a provider-isolated, local-only contract for a temporary
Cloud Run FastAPI demonstration host. The tracked templates are intentionally
not deployable: owner-controlled values remain explicit placeholders, and the
validator rejects them in deployable mode. No cloud or Vercel operation is
implemented by the wizard.

The hosting seam remains the existing FastAPI container interface and Vercel
same-origin `/api/v1/*` browser interface. GCP-specific configuration is local
to `deploy/gcp-demo/`; no application or protocol fork was created.

## Starting point and scope

- Requested fixed-base label: `b13bdb8f` (does not resolve in `.git-local`).
- Actual starting commit and review base:
  `b13bdb8df1a69015d283f5760df2ef28c2adec4c`
  (`docs: record GCP demo hosting feasibility`).
- Branch: `feat/gcp-demo-host`.
- Authorized scope: local templates, static tests and validator, a
  non-mutating future-owner wizard, runbook, and this report.
- No PRD, Development Plan, Solidity, deployment fact, backend business logic,
  database schema, worker protocol, or browser-auth invariant changed.

## TDD evidence

The agreed public seams were the Cloud Run service template, safe rewrite
template plus validator CLI, and wizard `--check`/`--plan` interface.

1. The first service-contract test failed with `FileNotFoundError` because the
   Cloud Run template did not exist, then passed after the minimal API-only
   template was added.
2. Rewrite and placeholder-refusal tests failed because the rewrite and
   validator did not exist, then passed after those interfaces were added.
3. Wizard refusal/plan tests failed with exit `127` because the wizard did not
   exist, then passed after the guarded local-only CLI was added.
4. Further contract cases cover `PORT`, readiness, pinned secret references, safe
   materialization, secret/identifier absence, frontend provider neutrality,
   and the absence of external mutation commands.

## Security and architecture invariants

- Cloud Run is API-only with request-based CPU, minimum zero, maximum two, and
  `RUNNERS_ENABLED=false`.
- The API command consumes Cloud Run's injected `PORT`; `/ready` is the startup
  probe.
- Database and JWT values are Secret Manager references, never tracked values.
- No real project, runtime identity, image digest, or Cloud Run origin is
  committed.
- The rewrite template is outside `frontend/` and cannot become a deployable
  `vercel.json` until a real HTTPS origin exists and the owner approves it.
- The browser still calls same-origin `/api/v1/*`; token/cookie/Origin/CORS
  behavior is unchanged.
- The deterministic fixture worker and five controlled runners stay on the
  owner laptop during demonstrations.
- OCI remains canonical; no OCI file is present, restored, modified, or
  required by the adapter.

## Verification

### Passing checks

- `python3 -m unittest scripts.tests.test_gcp_demo_adapter -v`: 15 passed.
- `ruff check scripts/validate_gcp_demo_config.py
  scripts/tests/test_gcp_demo_adapter.py`: passed.
- `ruff format --check scripts/validate_gcp_demo_config.py
  scripts/tests/test_gcp_demo_adapter.py`: passed.
- `python3 -m json.tool deploy/gcp-demo/cloud-run-service.template.yaml` and
  `python3 -m json.tool deploy/gcp-demo/vercel-rewrite.template.json`: passed.
- `python3 scripts/validate_gcp_demo_config.py --template --service
  deploy/gcp-demo/cloud-run-service.template.yaml --rewrite
  deploy/gcp-demo/vercel-rewrite.template.json`: passed.
- `bash -n scripts/gcp_demo_owner_wizard.sh`: passed.
- `scripts/gcp_demo_owner_wizard.sh --check`: passed without account, network,
  credential, build, upload, or deployment action.
- `scripts/gcp_demo_owner_wizard.sh --plan`: passed and performed no action.
- From `backend/`, `UV_CACHE_DIR=/tmp/nebula-uv-cache uv run --frozen --extra
  dev pytest -q tests/test_auth_security.py tests/test_health.py`: 19 passed.
- From `frontend/`, `npm test`: 3 passed; `npm run build`: passed; `npm run
  lint`: passed.
- `git --git-dir=.git-local --work-tree=. diff --check
  b13bdb8df1a69015d283f5760df2ef28c2adec4c`: passed.
- High-confidence secret scan with `rg -l --pcre2` for private-key headers,
  Google/AWS/GitHub/Slack token signatures, and credential-bearing HTTP(S)
  URLs across the changed non-test artifacts: no matches. The focused test
  separately scans both tracked GCP templates for these and PostgreSQL
  credential patterns, real service-account identifiers, and real Cloud Run
  origins.

### Explicit limitations and inherited findings

- Docker Desktop's CLI shim is installed, but Docker WSL integration is not
  enabled, so daemon-backed Docker validation could not run. The existing
  Dockerfile entry point, adapter command override, JSON/config parser, and
  contract tests were checked statically instead.
- Adding the backend deployment-config test module produces three expected
  failures because this GCP copy intentionally excludes `deploy/oci/` and
  `scripts/be002_production_auth_wizard.sh`. Those files were not restored and
  the adapter does not require them.
- `npm ci` reported 13 vulnerabilities in the existing lockfile dependency
  graph (5 moderate, 6 high, 2 critical). Dependency remediation is outside
  this provider-adapter slice; no package manifest or lockfile changed.

## Fixed-base review

Independent Standards and Spec reviews examined
`b13bdb8df1a69015d283f5760df2ef28c2adec4c...HEAD`.

- Standards found two minor error-boundary issues: malformed but valid JSON
  shapes and malformed URL-parser input could emit tracebacks. Regression
  tests reproduce both cases; the validator now rejects both cleanly, and all
  15 focused tests pass.
- Spec found that an attempted unrelated `.gitignore` repair would newly track
  two environment examples. That change and both additions were removed from
  GCP-001.
- Spec also required a stronger OCI-isolation test, exact verification/secret
  scan evidence, and an unconditional verdict. Those are now present.
- Final reviewer confirmation found no remaining blocker, major, or minor
  finding. Docker/provider-side validation remains a declared limitation.

## Skill usage

### Discovered

`solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`,
`diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`,
`improve-codebase-architecture`, `handoff`, `ask-matt`,
`setup-matt-pocock-skills`, `teach`, and `wizard`.

### Applied

1. **tdd** — each new public seam began with an observed failing behavior and
   progressed through small red-green slices; tests assert observable adapter
   contracts rather than helper implementation details.
2. **codebase-design** — the GCP adapter sits at the existing container and
   same-origin routing seam. Provider details stay local, and deleting the GCP
   directory, wizard, runbook, and generated future rewrite removes the
   experiment without application conditionals.
3. **domain-modeling** — concrete hosted/laptop and rollback scenarios were
   checked against `CONTEXT.md`; AI user, GPU provider, GPU node, worker,
   worker signer, lease, proof envelope, verifier, verdict, and settlement
   remain distinct. No glossary decision changed, so `CONTEXT.md` was not
   edited.
4. **wizard** — the future seven-stage owner journey is named in order, but the
   GCP-001 script captures no values and refuses every mutating mode. It only
   checks local prerequisites/templates or prints the plan.
5. **diagnosing-bugs** — applied its evidence-first loop when the existing
   environment-example tracking test failed; `git check-ignore` isolated rule
   precedence in `.gitignore`. Review then correctly classified that repair as
   outside GCP-001, so it was not retained.
6. **code-review** — Standards and Spec reviews are run independently against
   the actual fixed base; findings and dispositions are recorded before the
   final commit.

### Not applied

- **solidity-foundry-security** — no Solidity, Foundry, ABI, deployed contract,
  or contract configuration changed.
- **research** — GCP-001 implements the already approved, current research
  record; it introduces no new external fact claim.
- **grill-with-docs** — the approved GCP-001 requirements and research record
  already define the slice and stop conditions.
- **improve-codebase-architecture** — no broad refactor was authorized.
- **handoff** — this completion report is sufficient; no separate temporary
  session-transition document is needed.
- **ask-matt** — skill routing was explicit in the request and `AGENTS.md`.
- **setup-matt-pocock-skills** — all required skills were already installed.
- **teach** — no teaching artifact was requested.

## External actions and remaining gates

No Google Cloud or Vercel authentication, API enablement, IAM/service-account
mutation, secret creation, image build/upload, Cloud Run resource creation,
Vercel/DNS change, credential use, or deployment occurred.

Every external stage remains owner-only and separately authorized: billing,
project/region, spend controls, IAM identities, secrets, image/digest,
deployment, public health, Vercel cutover, browser acceptance, rollback, and
OCI switch-back.

## Verdict and next safe ticket

**GCP-001 is complete for its authorized local, API-only design and adapter
contract scope.** It does not establish a deployed or publicly accepted GCP
service.

The next safe ticket is **GCP-002: deployment configuration threat model and
owner-wizard design review**. It should extend the existing
deployment threat model for public Cloud Run ingress, Vercel hostname trust,
Secret Manager delivery, IAM separation, abuse/cost controls, evidence,
rollback, and OCI switch-back. It must remain local and non-mutating unless the
owner separately authorizes an exact external operation.
