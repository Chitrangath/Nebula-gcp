# DPL-005 Completion Report

Ticket: DPL-005 — Deployment runbook and local readiness report
State: completed locally; Stage 1 closed; Stage 2 remains owner-controlled
Starting commit: `bfa17b1` with a clean working tree

## Scope and files

Added:

- `docs/runbooks/ARBITRUM_SEPOLIA_DEPLOYMENT.md`
- `docs/research/DPL005_DEPLOYMENT_PRIMARY_SOURCES.md`
- this completion report

Updated:

- `.env.example`: removed the nonexistent public Arbitrum Sepolia WebSocket
  assumption and left the optional provider-specific value blank
- `docs/POST_PHASE3_SUB_TICKETS.md`: marked DPL-005 done

No Solidity, ABI, storage layout, backend, frontend, worker, database, or
production runtime behavior changed.

## Interface and security decisions

The runbook separates four states that must never be conflated:

```text
local readiness -> public-network dry run -> owner-authorized broadcast
-> receipt/getter/code verification -> explorer source verification
```

It documents exact preflight, local rehearsal, no-broadcast preview, approval,
broadcast, receipt, getter, bytecode, source-verification, manifest, recovery,
retirement, and secret-cleanup procedures. Every irreversible or external
action is explicitly owner-controlled.

The current deployment script reads a testnet deployer key from
`NEBULA_DEPLOYER_PRIVATE_KEY`. The runbook therefore requires an ignored,
permission-`600` local env file and forbids a literal key argument. A future
encrypted-keystore adapter requires its own reviewed slice; DPL-005 does not
silently change the deployed script interface.

The contract is non-upgradeable. "Rollback" is correctly defined as pausing,
stopping consumers, reconciling liabilities, preserving evidence, deploying a
replacement with fresh authorization, and migrating only after a new manifest
validates. It never implies chain history can be reversed.

## Verification evidence

### Smart contracts and deployment tooling

```text
forge fmt --check                         PASS
forge build                               PASS
forge test                                PASS: 157, 0 failed, 0 skipped
forge test -vvvv                          PASS: 157, 0 failed, 0 skipped
forge test --gas-report                   PASS
forge snapshot --check                    PASS
forge coverage --ir-minimum --report summary
                                            PASS
Overall coverage                          98.12% lines, 95.76% statements
Stateful invariants                        5 x 25,600 calls, 0 handler reverts
deployment validator/ignore tests         PASS: 15
sync_contract_artifacts.py --check         PASS
```

### Two fresh-Anvil rehearsals

The DPL-003 smoke script was executed without `--broadcast` against two
separately started Anvil processes:

```text
127.0.0.1:8547 -> chain 31337 -> SIMULATION COMPLETE -> exit 0
127.0.0.1:8548 -> chain 31337 -> SIMULATION COMPLETE -> exit 0
estimated gas on each run: 4,368,123
```

Both processes were stopped. Generated smoke dry-run journals/cache entries
were removed after inspection and were not committed.

### Backend and PostgreSQL

The full backend suite ran with `DATABASE_URL` rewritten in-process from the
existing local credentials so the database name was exactly `nebula_test`.
The command did not print the URL or credentials.

The first sandboxed attempt was invalid as a code signal: localhost PostgreSQL
and Anvil sockets returned `Operation not permitted`, and uv could not write
its user cache. The unchanged suite was rerun with permission for local-only
services and a writable temporary uv cache:

```text
pytest -q -ra                             PASS: 321, 0 failed, 0 skipped
uv run --offline ruff check .             PASS
uv run --offline ruff format --check .    PASS: 75 files formatted
```

One non-failing pytest deprecation warning remains for the existing custom
`event_loop_policy` fixture. It is not caused by DPL-005.

### Safety and consistency

```text
manifest schema JSON parse                PASS
manifest validator Ruff                   PASS
manifest validator strict MyPy            PASS
git diff --check                          PASS
secret/high-entropy scan                  PASS
Foundry broadcast/cache cleanup           PASS
```

## Primary-source validation

Official Arbitrum, Circle, and Foundry sources were rechecked on 2026-09-09.
The research note records chain `421614`, public HTTP RPC and explorers,
Circle's Arbitrum Sepolia test USDC and faucet, the Foundry
simulation/`--broadcast` boundary, source-verification behavior, and mutable
facts that must be checked again immediately before deployment.

## Test-first record

DPL-005 adds operator documentation rather than executable production
behavior, so no new code test seam was introduced. Every command presented as
a Stage 1 gate was executed against the existing public interfaces. Earlier
DPL-001 through DPL-004 reports retain their red-green evidence for deployment,
smoke, manifest, and ignore behavior.

## Skill usage

### Discovered

`solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`,
`diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`,
`improve-codebase-architecture`, `handoff`, `ask-matt`,
`setup-matt-pocock-skills`, `teach`, and `wizard`.

### Applied

1. `solidity-foundry-security`: complete deployment/security gate, invariant,
   coverage, gas, role, chain, secret, immutable, recovery, and rollback review.
2. `research`: primary-source network, Circle USDC/faucet, Foundry broadcast,
   and verification facts were captured in a cited repository note.
3. `codebase-design`: the runbook follows the existing validated deployment,
   smoke, artifact, and manifest interfaces instead of introducing alternatives.
4. `code-review`: independent standards and specification review of the DPL-005
   documentation and readiness evidence.

### Not applied

- `tdd`: no new executable behavior was implemented; existing public commands
  were exercised as acceptance gates instead.
- `domain-modeling`: existing vocabulary was used without changing a domain
  term or relationship.
- `diagnosing-bugs`: the initial backend errors were identified as sandbox
  denials by their direct exceptions and disappeared unchanged under local-only
  permission; no product bug was diagnosed or fixed.
- `wizard`: the roadmap expressly defers an executable owner wizard until its
  stages and destinations are reviewed with the owner.
- Remaining routing, refactoring, setup, teaching, and handoff skills were not
  needed for this documentation/readiness slice.

## External actions and owner handoff

No public RPC call, wallet use, faucet request, secret creation, broadcast,
transaction, contract deployment, explorer publication, hosted-resource
change, push, merge, tag, or release occurred. Specifically: **no external
transaction was broadcast**.

Local rehearsal is green. Stage 2 remains blocked until the owner returns and
provides/approves only the required public identity map, funds testnet roles,
and provisions secret RPC/explorer credentials outside Git and chat. The next
single ticket is HUM-001; its owner-controlled gate must not be bypassed.

## Files awaiting commit

- `.env.example`
- `docs/runbooks/ARBITRUM_SEPOLIA_DEPLOYMENT.md`
- `docs/research/DPL005_DEPLOYMENT_PRIMARY_SOURCES.md`
- `docs/DPL005_COMPLETION_REPORT.md`
- `docs/POST_PHASE3_SUB_TICKETS.md`
