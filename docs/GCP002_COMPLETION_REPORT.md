# GCP-002 Deployment Readiness Completion Report

## Outcome

GCP-002 converts the GCP copy from an inert adapter contract into a reviewed
deployment-readiness assessment. It does not perform deployment. The approved target
is Vercel frontend, public Cloud Run FastAPI API, Supabase PostgreSQL, and the
existing Arbitrum Sepolia contract, with the worker and five controlled runners
on the owner laptop only during supervised tests and faculty demonstrations.

Cloud Run remains API-only. The validator now rejects runner-named environment
configuration and runner commands in addition to requiring one `api` container
and `RUNNERS_ENABLED=false`.

The assessment found a blocking application-adapter gap: the API currently
uses instance-local `FileStorage`, which is disposable and cannot be shared
with the owner-laptop worker, and the GCP service contract lacks complete
chain/storage runtime configuration. GCP-002 is complete as an assessment, but
the environment is not ready for cloud mutation.

## Fixed point and authorized scope

- GCP-001 base: `912e2085370494071b8df6ded4e9512402f1275d`.
- Branch: `feat/gcp-demo-host`.
- Changed scope: GCP validator/tests, non-mutating owner-wizard plan, GCP-copy
  PRD deployment sections, GCP runbook, current research, provider-specific
  threat model, and this report.
- Unchanged: Solidity, deployed contract facts, ABI, backend protocol/business
  logic, database schema, worker protocol, browser-auth invariants, original
  OCI files, and Development Plan.

## TDD record

The agreed test seams were the existing deployment adapter interface and the
wizard `--plan` interface.

1. A materialized service with `RECEIPT_RUNNER_ENABLED=true` was initially
   accepted. The validator now rejects every runner-named setting other than
   the required false `RUNNERS_ENABLED`, and rejects runner commands.
2. The ordered eleven-gate wizard test initially failed because the GCP-001
   seven-stage plan lacked project, budget, API, IAM, secret, image, distinct
   health, and browser gates. The GCP-002 plan now exposes all eleven in order
   while retaining no mutation command.
3. PRD topology, threat-category, and Docker-evidence tests initially failed
   because the GCP-002 records did not exist. The narrow deployment amendment,
   provider threat model, and evidence section now satisfy those contracts.

## Deployment-readiness design

The hosting seam is unchanged: the frontend calls same-origin `/api/v1/*`, a
reviewed Vercel external rewrite maps it to Cloud Run `/v1/*`, and the existing
FastAPI container consumes the injected `PORT`. Provider complexity remains in
`deploy/gcp-demo/`, its validator, the owner wizard, and GCP documents. No GCP
conditional entered application code.

The owner journey has eleven explicit gates: project/region/billing, budgets,
APIs, IAM, secrets, immutable image, Cloud Run, public health, Vercel cutover,
browser authentication, and rollback/OCI switch-back. In GCP-002 the wizard
only prints this journey or validates local files; it cannot execute a gate.

## Current primary-source conclusions

The dated source record is
`docs/research/GCP002_DEPLOYMENT_READINESS_SOURCES.md`. Official Google and
Vercel documentation confirms:

- request-based Cloud Run with minimum zero is suitable for a sporadic API but
  not continuous runners;
- the public `run.app` origin remains directly reachable behind a rewrite;
- runtime and deployer identities should be separate, with exact-secret access
  granted only to the runtime identity and no downloaded service-account key;
- secret environment references should use numbered versions;
- budget alerts do not cap costs, eligible spend caps trade availability for
  containment, and maximum instances are not a monetary ceiling;
- Vercel external rewrites preserve the browser URL and authenticated API
  caching must remain explicitly disabled; and
- Cloud Run and Vercel rollback both require renewed health and browser-auth
  acceptance.

## Prior local Docker evidence

The 2026-10-16 post-GCP-001 check built
`nebula-gcp001-api-dockercheck:912e208`, started one API-only container with
dummy values, `RUNNERS_ENABLED=false`, and injected `PORT=18081`, then observed
`/live` `200` and `/ready` `503` against a deliberately unreachable dummy
database. The named container and image were removed and the worktree remained
clean. This resolves local build/startup/liveness validation but does not prove
positive database-backed readiness; deployed Supabase `/ready` `200` remains a
GCP-004 acceptance gate after local GCP-003 closure.

## Verification

### Passing checks

- `python3 -m unittest scripts.tests.test_gcp_demo_adapter -v`: 22 passed.
- `ruff check scripts/validate_gcp_demo_config.py
  scripts/tests/test_gcp_demo_adapter.py`: passed.
- `ruff format --check scripts/validate_gcp_demo_config.py
  scripts/tests/test_gcp_demo_adapter.py`: passed.
- `bash -n scripts/gcp_demo_owner_wizard.sh`: passed.
- `python3 -m json.tool` for both tracked GCP templates: passed.
- `python3 scripts/validate_gcp_demo_config.py --template --service
  deploy/gcp-demo/cloud-run-service.template.yaml --rewrite
  deploy/gcp-demo/vercel-rewrite.template.json`: passed.
- `scripts/gcp_demo_owner_wizard.sh --plan`: printed all eleven gates and
  performed no action; `--check` passed without contacting Docker or any
  account/network service.
- From `backend/`, `UV_CACHE_DIR=/tmp/nebula-uv-cache uv run --frozen --extra
  dev pytest -q tests/test_auth_security.py tests/test_health.py`: 19 passed.
- From `frontend/`, `npm test`: 3 passed; `npm run build`: passed; `npm run
  lint`: passed.
- `git --git-dir=.git-local --work-tree=. diff --check`: passed after all
  changed and new files were staged.
- Changed-path guard found no Solidity, backend application, migration, worker,
  frontend source, OCI, or Development Plan change.
- High-confidence scan for private-key headers, Google/AWS/GitHub/Slack token
  signatures, and credential-bearing HTTP(S) URLs across changed artifacts:
  no matches. Focused tests separately reject credential-bearing PostgreSQL
  URLs, real service-account IDs, and real Cloud Run origins in GCP templates.

### Verification boundary

GCP-002 does not repeat or promote the earlier Docker result into deployed
evidence. It records that result as local historical evidence and preserves its
unproven positive database-readiness boundary. No GCP or Vercel verification
was possible or authorized in this ticket.

## Fixed-base review

Independent Standards and Spec reviews examined
`912e2085370494071b8df6ded4e9512402f1275d...HEAD`.

- Standards identified one blocker: the connected job flow cannot use the
  current instance-local `FileStorage` across Cloud Run instances and the
  owner-laptop worker, and the template omits required chain configuration.
  The deployment verdict is now blocked and the exact local closure work is
  recorded; no unauthorized backend change was made.
- Spec identified the incomplete secret/config inventory. The threat model now
  classifies database, JWT, R2, credential-bearing RPC, public deployment,
  forbidden signer, and excluded Pinata settings.
- Spec identified a stale Vercel cache-default sentence. It now reflects the
  April 2026 external-origin behavior while preserving explicit cache opt-out.
- Both reviews identified the pending report verdict. It is now unconditional
  below.

## Skill usage

### Discovered

`solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`,
`diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`,
`improve-codebase-architecture`, `handoff`, `ask-matt`,
`setup-matt-pocock-skills`, `teach`, and `wizard`.

### Applied

1. **research** — a background research pass used only current official Google
   Cloud and Vercel sources and produced one dated source record.
2. **codebase-design** — preserved the container and same-origin routing seam;
   the GCP adapter remains deletable without redistributing provider logic into
   FastAPI, the frontend, worker, or protocol.
3. **domain-modeling** — checked concrete hosted/laptop scenarios against
   `CONTEXT.md`; worker, worker signer, GPU node, verifier, verdict, and
   settlement remain distinct. No glossary meaning changed, so `CONTEXT.md`
   was not edited.
4. **tdd** — captured runner-injection, ordered owner-gate, topology, threat,
   and evidence behavior as failing tests before implementation.
5. **wizard** — mapped each approved future stage, its output, and secret
   handling in the runbook; the executable remains a non-mutating plan/check
   interface because external actions are forbidden in this ticket.
6. **code-review** — independent Standards and Spec passes reviewed the
   committed fixed-base diff; their blocker/minor findings and dispositions are
   recorded above.

### Not applied

- **solidity-foundry-security** — no Solidity, Foundry, ABI, contract
  configuration, or deployment fact changed.
- **diagnosing-bugs** — no unexpected product failure required diagnosis; the
  expected failing cases were handled through TDD.
- **grill-with-docs** — the owner supplied the target topology, required gates,
  scope, and stop condition directly.
- **improve-codebase-architecture** — no broad refactor was needed or allowed.
- **handoff** — no session transition document is needed; this report and the
  runbook are durable records.
- **ask-matt** — skill routing was explicit in the request and `AGENTS.md`.
- **setup-matt-pocock-skills** — the required skills were already installed.
- **teach** — no teaching artifact was requested.

## External actions and cost-bearing changes

No Google Cloud or Vercel authentication, project creation, billing linkage,
API enablement, IAM/service-account change, secret creation, image build or
upload, registry change, Cloud Run deployment, Vercel cutover, DNS change, or
credential use occurred. GCP-002 incurred no cloud resource mutation.

## Verdict and next ticket

**GCP-002 is complete as a deployment-readiness assessment, with deployment
blocked.** It does not authorize a health/auth-only partial public service or
any cloud mutation.

The immediate next safe ticket is **GCP-003: provider-neutral durable storage
and complete Cloud Run runtime-configuration closure**. It is local-only: add
and test a shared durable `StorageBackend` adapter, configure it without
changing storage semantics, materialize every required secret/public setting
through validated placeholders, and prove a container-to-laptop-worker flow
against non-production storage.

After GCP-003 passes review, the exact next owner-authorized deployment ticket
is **GCP-004: owner-gated GCP foundation, immutable image, Cloud Run API
deployment, and direct health acceptance**. GCP-004 may execute owner gates
1–8 with immediate confirmation at each mutation and must stop after direct
Cloud Run `/live` and Supabase-backed `/ready` evidence. Vercel cutover and
real-browser acceptance remain a later ticket.
