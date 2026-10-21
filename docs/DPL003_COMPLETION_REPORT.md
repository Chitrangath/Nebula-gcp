# DPL-003 Completion Report

Ticket: DPL-003 — Bounded local lifecycle smoke script
State: completed locally; no external broadcast
Starting commit: `d194ed7`

## Scope and implementation

Added `contracts/script/Smoke.s.sol`, a chain-locked local rehearsal that uses
six nonzero, pairwise-distinct identities: deployer, owner, backend verifier,
AI user, GPU provider payout wallet, and worker signer. Addresses are loaded
from named environment variables; the script never reads a private key.

The script rejects any chain other than Anvil chain ID `31337` before its first
deployment action. It then deploys a fresh owner-mintable six-decimal
`LocalMockUSDC`, reuses the validated DPL-002 deployment path, and executes:

```text
deploy -> configure verifier/owner -> mint -> approve -> create
-> verifier assigns provider -> verifier submits proof
-> valid verdict -> exact provider pending credit -> provider withdrawal
-> second job -> invalid verdict -> exact AI-user pending refund -> withdrawal
```

It additionally proves unauthorized assignment and settlement fail with exact
errors, duplicate settlement fails, owner pause blocks job creation, unpause
restores operation, and solvency holds after every accounting transition and
at the final zero-liability state. It uses the contract's canonical interface
and UUID layout and does not introduce another ABI, proof verifier, Merkle, or
EIP-712 implementation.

`Deploy.s.sol` received only the protected seam needed for unlocked local
Anvil identities. Its production entry point retains the validated private-key
broadcast path and behavior.

## Test-first evidence

`contracts/test/Smoke.t.sol` was written before the smoke implementation. The
first focused run failed because `script/Smoke.s.sol` did not exist. The final
five tests cover the complete separated-role journey, environment loading,
zero and duplicate identities, and wrong-chain rejection before deployment.

The first script rehearsal also exposed that expected reverts inside a Forge
broadcast queue make the overall simulation fail even when `expectRevert`
matches. Negative checks were moved to local impersonated calls; successful
state transitions remain attributed to their distinct unlocked identities.

## Fresh-Anvil acceptance evidence

The reviewed script ran successfully, without `--broadcast`, against two
separately started fresh Anvil processes:

```text
Anvil 1: http://127.0.0.1:8547, chain 31337, SIMULATION COMPLETE, exit 0
Anvil 2: http://127.0.0.1:8548, chain 31337, SIMULATION COMPLETE, exit 0
Estimated script gas on each run: 4,368,123
```

Both processes were stopped after their run. Forge's generated dry-run
transaction/cache files were removed and are not part of this ticket.

## Verification

```text
forge fmt --check                         PASS
forge build                               PASS
forge test --match-path test/Smoke.t.sol  PASS: 5
forge test --match-path test/Deploy.t.sol PASS: 9
forge test                                PASS: 157, 0 failed, 0 skipped
forge test -vvvv                          PASS
forge test --gas-report                   PASS
forge snapshot --check                    PASS
forge coverage --ir-minimum --report summary
                                            PASS
Smoke.s.sol coverage                      98.15% lines, 93.39% statements,
                                          100% functions
LocalMockUSDC.sol coverage                100% lines/statements/functions
Overall coverage                          98.12% lines, 95.76% statements
Stateful contract invariants               5 x 25,600 calls, 0 handler reverts
sync_contract_artifacts.py --check         PASS
secret scan                               PASS
git diff --check                          PASS
```

Foundry emitted only the known read-only signature-cache warning and
pre-existing timestamp lint warnings. Coverage used the repository's
documented `--ir-minimum` workaround.

## Two-axis review

Fixed point: `d194ed7`.

### Standards

The initial review found one high-severity ordering issue: MockUSDC could be
deployed before the local chain was checked. The script now performs an
explicit chain-31337 preflight before its first broadcast, with a regression
test. No secrets were found.

### Specification

The initial review found one medium gap: valid and invalid settlement credits
were only implied by final balances. Exact recipient and total pending-credit
assertions now execute before each withdrawal. The required two-fresh-Anvil
evidence is recorded above. No requirement remains open.

## Skill usage

### Discovered

`solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`,
`diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`,
`improve-codebase-architecture`, `handoff`, `ask-matt`,
`setup-matt-pocock-skills`, `teach`, and `wizard`.

### Applied

1. `solidity-foundry-security`: role/chain threat analysis, exact revert checks,
   accounting assertions, invariant regression, coverage, gas, and secret gates.
2. `tdd`: missing-script red state, focused green tests, and regression tests
   for the discovered chain-ordering defect.
3. `domain-modeling`: preserved the distinct owner, verifier, AI user, GPU
   provider, and worker-signer roles from `CONTEXT.md`.
4. `codebase-design`: reused DPL-002 deployment/configuration seams and the
   canonical contract interface rather than duplicating protocol logic.
5. `code-review`: independent fixed-base standards and specification reviews,
   followed by remediation and verification.

### Not applied

- `diagnosing-bugs`: no pre-existing production defect was diagnosed.
- `research`: no new external fact was required for a local-only ticket.
- `wizard`: no human-only provisioning or credential workflow occurred.
- Remaining routing, refactoring, setup, teaching, and handoff skills were not
  relevant to this bounded implementation.

## External actions and next gate

No wallet, faucet, real secret, public RPC, transaction, deployment, explorer
action, commit, push, or hosted resource was used. DPL-004 is the next
unblocked ticket: sanitized deployment-manifest generation and validation.
