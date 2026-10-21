# GCP-003 Completion Report

**Date:** 2026-10-16

**Fixed review base:** `cbc1a25bd912a7e0c421e741cc068563980e0aa9`

**Scope:** local provider-neutral durable storage and Cloud Run runtime-configuration closure only

## Outcome

GCP-003 adds one provider-neutral `StorageBackend` construction seam with two
adapters: private local `FileStorage` for development/tests and private
S3-compatible `S3Storage` for the approved Cloud Run/R2 demo topology. FastAPI
and the controlled laptop runners now select storage through the same runtime
configuration. No database schema, worker protocol, contract fact, chain role,
proof/escrow semantics, or browser-auth invariant changed.

The Cloud Run template now requires `STORAGE_ADAPTER=s3`; it cannot select
instance-local storage. Its validator fails closed unless database, exact
frontend origin, JWT lifetimes, RPC, preserved Arbitrum Sepolia identifiers,
deployed contract identifiers, private bucket/account/prefix, pinned storage
credential secrets, and `RUNNERS_ENABLED=false` are complete and non-placeholder.

This closes the local application/configuration blocker. It does not prove a
remote provider integration and is not deployment evidence.

## Storage contract and security properties

- One validated relative-POSIX key vocabulary covers accepted inputs,
  model artifacts, results, and proof envelopes.
- Empty, absolute, traversing, repeated-separator, backslash, control-character,
  and over-1,024-byte keys fail before an adapter call.
- The remote adapter sends no public ACL and assumes no public bucket/domain.
- Immutable objects use atomic `IfNoneMatch="*"`; only an exact-byte retry is
  accepted after a conditional conflict.
- Provider failures are translated to an application storage-unavailable error;
  existing database-failure paths retain compensating deletion.
- Presigned capabilities, if needed later, are one operation on one exact key
  and bounded by the configured maximum (300 seconds in the GCP profile).
- The current laptop worker continues to use authenticated backend input/model
  routes and result upload; storage credentials do not enter the frontend or
  worker protocol.

## Test-first record

Focused tests were added before implementation and initially failed at import
because `S3Storage`, configuration/factory types, and object-key helpers did not
exist. GCP profile tests then failed because the template had no durable adapter
selection or complete runtime inventory. Implementation proceeded only after
those red states were recorded.

Local fake-client proof covers FileStorage compatibility, private remote PUTs,
exact-key/short-TTL capabilities, conditional immutable retry/conflict,
provider write failure without a partial object, traversal/key rejection,
missing/unsupported configuration, and independent API/laptop adapters sharing
one fake backing store.

## Verification

- `backend/.venv/bin/pytest -q backend/tests/test_durable_storage.py`: **19 passed**.
- Focused upload/result/proof regressions (`test_job_input_upload.py`,
  `test_worker_completion_protocol.py`, `test_output_bytes.py`,
  `test_proof_pipeline.py`): **31 passed**.
- `python3 -m pytest -q worker/tests/test_protocol_convergence.py`: **3 passed**
  (warnings only).
- `python3 -m unittest scripts.tests.test_gcp_demo_adapter -q`: **24 passed**.
- Ruff check on all changed Python files: **passed**; Ruff formatting: **passed**.
- Targeted strict mypy for `app/services/storage.py` with third-party imports
  skipped: **passed**. The repository-wide strict mypy command still exposes
  extensive pre-existing SQLAlchemy/untyped-dependency failures outside this
  ticket.
- Template JSON parsing, GCP validator template mode, wizard `--check`, wizard
  `--plan`, and `bash -n`: **passed**. The wizard contacted no account or Docker
  daemon and performed no mutation.
- Broader backend execution reached relevant tests, but the unfiltered suite is
  not a valid pass gate in this intentionally OCI-pruned copy: Anvil connection
  tests cannot connect, OCI deployment tests reference excluded `deploy/oci/`,
  and a long-standing async SQLite teardown stall appears in large combined
  runs. The focused changed-path regressions above completed cleanly.

Final `git diff --check`, secret scan, changed-path guard, and the required
two-axis fixed-base code review are recorded in the final handoff.

## Fixed-base review dispositions

The first independent Standards/Spec review of
`cbc1a25bd912a7e0c421e741cc068563980e0aa9...HEAD` found two major issues and
one documentation-standard issue. Immutable-write conflicts could trigger
cleanup of an object the current request did not create, non-`ClientError`
provider outages were not consistently normalized or mapped to bounded 503
responses, and public storage interfaces lacked concise docstrings.

The implementation now returns an immutable-write ownership result, performs
compensating deletion only when that request created the object, logs cleanup
failure without masking the primary error, normalizes botocore transport/body/
presign failures, maps runtime read failures to 503, and documents the public
contract. Regression tests cover conflict ownership and non-`ClientError`
outages. Both reviewers re-check the amended commit before closure.

## Local proof versus unperformed provider proof

The local adapter proof establishes interface behavior and S3-compatible
request construction with a fake client. It does **not** establish that an R2
bucket exists, an object token is bucket scoped, Secret Manager grants are
correct, the real endpoint accepts the client configuration, conditional
writes behave correctly at that provider, Cloud Run and the laptop exchange
objects, cleanup works during provider faults, or storage latency/egress is
acceptable. GCP-003 therefore makes no deployed, fully hosted, real GPU,
continuous-runner, SLA, or production-readiness claim.

## Skill usage

### Discovered

`solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`,
`diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`,
`improve-codebase-architecture`, `handoff`, `ask-matt`,
`setup-matt-pocock-skills`, `teach`, and `wizard`.

### Applied

1. **tdd** — recorded failing storage and deployed-profile behavior before
   adding each implementation seam.
2. **codebase-design** — kept provider mechanics behind the existing deep
   `StorageBackend` boundary and centralized construction/config validation.
3. **domain-modeling** — preserved accepted input, model artifact, result,
   proof envelope, worker, runner, verifier, and settlement meanings.
4. **research** — used current official Cloudflare R2, AWS/Boto3, and Google
   Cloud sources in `docs/research/GCP003_DURABLE_STORAGE_SOURCES.md`.
5. **wizard** — added only future owner gates for private bucket, scoped token,
   pinned secrets, and cross-runtime acceptance; executable mutations remain
   unavailable.
6. **code-review** — the committed fixed-base diff receives independent
   Standards and Spec reviews before final completion.

### Not applied

- **solidity-foundry-security** — Solidity, Foundry, ABI, and contract facts did
  not change.
- **diagnosing-bugs** — expected TDD failures and known environment exclusions
  did not require a product-bug diagnosis workflow.
- **grill-with-docs** — the owner supplied a complete ticket and acceptance
  boundary.
- **improve-codebase-architecture** — no broad refactor was needed.
- **handoff** — this completion report is sufficient; no session transition
  document is needed.
- **ask-matt** — routing was explicit in the ticket and `AGENTS.md`.
- **setup-matt-pocock-skills** — required skills were already installed.
- **teach** — no teaching artifact was requested.

## GCP-004 owner-only gates

GCP-004 may proceed only with immediate owner confirmation at every mutation:

1. approve exact GCP project, region, billing account, budgets, alerts, and cost exposure;
2. enable only required Cloud Run, Artifact Registry, and Secret Manager APIs
   (plus Cloud Build only if separately chosen);
3. create one private R2 demo bucket with no public domain or `r2.dev` access;
4. create a bucket-scoped Object Read & Write token and least-privilege GCP
   runtime/deployer identities, with no downloaded service-account key;
5. create exact secrets with numbered versions for database, JWT, RPC, and R2
   credentials; review all non-secret chain/storage values;
6. build, scan, review, upload, and record one immutable image digest;
7. deploy the API-only Cloud Run service with min instances zero, low max
   instances, request billing, no signing key, and no runners;
8. prove direct public `/live` 200, Supabase-backed `/ready` 200, and bounded
   unavailable-database `/ready` 503;
9. prove non-production Cloud Run-write/laptop-read and laptop-write/Cloud
   Run-read/delete behavior with sanitized hash evidence;
10. stop before Vercel cutover, which remains a separately approved stage
    followed by real-browser auth smoke and rollback acceptance.

OCI remains canonical in the original repository throughout.
