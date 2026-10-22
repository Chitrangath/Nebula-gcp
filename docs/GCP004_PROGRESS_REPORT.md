# GCP-004 Progress Report

**Status:** in progress; no Cloud Run, Artifact Registry, Secret Manager, IAM,
R2, Vercel, or DNS mutation has been performed by this report

## Outcome so far

- Added an Ubuntu/WSL bootstrap path for the Google Cloud CLI and console-based
  authentication.
- Migrated repository-integrity checks from the removed `.git-local` metadata
  to the active Git repository.
- Verified the owner-selected `nebula-demo-chitrangath` project is active and
  billing-enabled using read-only commands.
- Added an isolated database-unavailable Cloud Run probe contract. It uses the
  same immutable image as the candidate API, receives no production traffic,
  uses a dummy unreachable database URL, starts on `/live`, must return
  `/live = 200` and `/ready = 503`, and is deleted before the gate passes.
- Preserved the production API configuration and Supabase database throughout
  the failure test.

GCP-004 is not complete. The real cloud deployment and direct private-storage
exchange remain owner-controlled, and the storage acceptance gate must be made
executable before `--run` is approved.

## Verification

- Combined setup, owner-wizard, and GCP adapter suite: **49 passed**.
- Python compilation passed for both renderers and the shared validator.
- Bash syntax passed for the E2E and GCP-004 wizards.
- `git diff --check` passed.

## Phase 7 skill usage

### Discovered skills

- `solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`,
  `diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`,
  `improve-codebase-architecture`, `handoff`, `ask-matt`,
  `setup-matt-pocock-skills`, `teach`, and `wizard`.

### Applied

1. **`wizard`**: retained typed confirmation immediately before system,
   authentication, cloud, IAM, public-access, and deletion actions; kept
   bootstrap and deployment as separate modes.
2. **`tdd`**: reproduced each bootstrap/readiness defect with a failing public
   CLI or renderer-contract test before implementation.
3. **`diagnosing-bugs`**: used deterministic CLI feedback loops for the removed
   `.git-local`, unreadable apt key, WSL browser callback, and missing database
   failure gate.
4. **`code-review`**: reviewed the deployment candidate separately against
   repository standards and GCP-004 requirements; the readiness-probe work
   addresses the database-failure finding.

### Not applied

- Solidity, domain-model changes, external research artifacts, architecture
  refactoring, teaching, skill setup, meta-routing, and session-handoff skills
  were outside this bounded deployment-wizard correction. Official Google CLI
  documentation was consulted directly for authentication behavior.
