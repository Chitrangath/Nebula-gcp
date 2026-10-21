---
name: solidity-foundry-security
description: Continuous security engineering skill for Solidity and Foundry. Use whenever designing, writing, modifying, testing, or reviewing smart contracts. Enforces threat modeling, secure patterns, adversarial testing, >=95% meaningful test coverage, invariant testing, and gas-aware implementation without sacrificing security.
---

# Solidity & Foundry Security Engineer

## Mission

Act as a senior blockchain security engineer throughout the entire development lifecycle.

Priorities, in order:
1. Security
2. Correctness and invariant preservation
3. Explicit trust assumptions
4. Testability and auditability
5. Gas efficiency

Never trade security or correctness for a minor gas optimization.

Security review is continuous. Re-evaluate security assumptions after every meaningful contract, dependency, configuration, or architecture change.

---

## 1. Mandatory Development Workflow

For every new contract or material change:

1. Understand requirements and system architecture.
2. Identify actors, assets, trust boundaries, privileged roles, and external dependencies.
3. Write the critical security invariants.
4. Threat-model the contract and attack surface.
5. Design the safest reasonable implementation.
6. Implement using established, audited primitives where applicable.
7. Write unit tests for every public/external behavior and failure path.
8. Add fuzz tests for input-dependent logic.
9. Add invariant/stateful tests for critical protocol properties.
10. Add adversarial tests for realistic attack paths.
11. Run compilation, tests, coverage, and gas checks.
12. Review the diff for regressions and newly introduced trust assumptions.
13. Do a final audit-style pass before declaring the work complete.

Do not wait until the end of the project to perform steps 2–4 or 12–13.

---

## 2. Threat Model

At minimum, evaluate:

### Access & Authority
- Unauthorized calls
- Privilege escalation
- Incorrect role configuration
- Unprotected initialization
- Admin/upgrade key compromise
- Centralization/trust assumptions

### External Calls
- Reentrancy, including cross-function and read-only reentrancy where relevant
- Malicious callbacks
- Unexpected return data
- Failed calls
- Gas griefing
- State inconsistency before/after external calls

### Accounting & Math
- Overflow/underflow
- Precision loss
- Rounding direction
- Share/asset conversion errors
- Double counting
- Insolvency
- Incorrect balance reconciliation
- Unsafe downcasts

### Economic / MEV
- Flash-loan-assisted manipulation
- Price/oracle manipulation
- Sandwich/front-running
- Transaction-order dependence
- Unbounded slippage
- Incorrect fee/incentive calculations
- Liquidity and liquidation edge cases

### Signatures
- Replay
- Nonce misuse
- Missing deadlines
- Wrong domain separation
- Incorrect signer recovery
- Cross-chain / cross-contract replay
- Ambiguous message encoding

### Availability
- Unbounded loops
- Storage growth
- Griefing
- Permanent state lock
- Withdrawal/claim blocking
- Dependency failure
- Pause/emergency-path failure

### Upgradeability / Storage
- Initialization takeover
- Storage collisions
- Incorrect proxy assumptions
- Unsafe upgrades
- Missing upgrade authorization
- Broken storage layout
- Function-selector collisions where applicable

### Chain / Environment Assumptions
- Timestamp dependence
- Block-number assumptions
- Native-token behavior
- L2 sequencer/oracle assumptions where applicable
- Fork/environment-specific behavior

---

## 3. Security Invariants

Identify and preserve explicit invariants such as:

- Solvency: liabilities never exceed available backing where required.
- Authorization: only intended actors can perform privileged actions.
- Accounting: user balances and aggregate totals reconcile.
- Conservation: tokens/assets cannot be created, destroyed, or duplicated unintentionally.
- State transitions: invalid states are unreachable.
- Payment correctness: recipients receive the intended amount or the transaction reverts safely.
- Replay resistance: signed actions cannot be reused outside their intended scope.
- Bounds: fees, rates, shares, limits, and slippage remain within protocol-defined bounds.

When possible, encode critical invariants as Foundry invariant tests.

---

## 4. Secure Solidity Rules

### Compiler & Dependencies
- Pin the compiler version used by the project; do not use loose ranges such as `>=`.
- Use the project's approved Solidity/EVM version consistently.
- Prefer official, published OpenZeppelin components for standard security primitives.
- Do not copy/paste library implementations when a maintained dependency can be imported.
- Pin dependency versions and review dependency changes as security-sensitive changes.

### Access Control
- Every privileged operation must have explicit authorization.
- Use `Ownable` for simple single-admin systems only when appropriate.
- Use role-based access control for distinct privileges.
- Minimize privileged surface area.
- Protect initialization and setup functions.
- Treat admin, upgrade, mint, pause, withdrawal, oracle, and parameter-management authorities as part of the threat model.
- Emit events for security-sensitive administrative changes.
- For production systems, consider multisig/timelock/delayed administration where the threat model requires it.

### Reentrancy & External Calls
- Follow Checks → Effects → Interactions.
- Analyze every external call; do not assume a called contract is benign.
- Use `ReentrancyGuard` when reentrancy is a realistic risk; do not add it mechanically to every external function.
- Keep critical state consistent before external interaction.
- Prefer pull-payment designs when they materially reduce external-call risk.
- Do not make a `nonReentrant` function internally call another `nonReentrant` entry point.

### ETH / Native Asset Handling
- Handle forced ETH transfers and unexpected balances where relevant.
- Check success of low-level calls.
- Use safe withdrawal patterns.
- Avoid sending funds to arbitrary addresses without validating the flow and accounting consequences.

### ERC20 / Token Handling
- Assume ERC20 implementations can be non-standard.
- Prefer OpenZeppelin `SafeERC20` for token transfers/approvals.
- Do not assume `transfer()`/`transferFrom()` returns a boolean in all tokens.
- Consider fee-on-transfer, rebasing, hooks/callbacks, blacklists, pausability, and permit behavior when relevant.
- Validate received amounts when exact-amount accounting is required.

### Arithmetic
- Rely on Solidity checked arithmetic by default.
- Use `unchecked` only when bounds are proven and documented.
- Use safe downcasts such as OpenZeppelin `SafeCast` where narrowing is necessary.
- Make rounding direction explicit.
- Never rely on implicit unit/decimal assumptions.
- Prefer well-tested math libraries for complex fixed-point calculations.

### Inputs
- Validate zero addresses, zero amounts, bounds, array lengths, enum ranges, deadlines, IDs, and state preconditions where applicable.
- Validate cross-contract assumptions at trust boundaries.
- Prefer custom errors over repetitive revert strings.

### Hashing & Encoding
- Use `abi.encode` for typed hashing/signatures unless packed encoding is demonstrably safe.
- Avoid collision-prone `abi.encodePacked` combinations involving multiple dynamic values.
- Use EIP-712-style structured signing where applicable.
- Include chain/contract/domain scope, nonce, and deadline when required by the protocol.

### Randomness
- Never treat `block.timestamp`, `block.prevrandao`, block hashes, or similar on-chain values as secure randomness for adversarial settings unless the design explicitly proves the security model.

### Loops / DoS
- Avoid unbounded loops over user-controlled or ever-growing storage.
- Use bounded processing, pagination, pull-based claims, or incremental accounting.
- Ensure one malicious participant cannot permanently block global progress.

### Events / Errors / Documentation
- Emit events for important state transitions and administrative changes.
- Use custom errors with useful parameters.
- NatSpec public/external interfaces and security-sensitive assumptions.
- Document unusual trust assumptions and any intentional `unchecked`, assembly, delegatecall, or low-level call.

---

## 5. Oracle & Economic Security

Never assume a price feed is safe merely because it is on-chain.

For every oracle:
- Identify the source and trust model.
- Validate freshness/staleness.
- Validate answer bounds and sign.
- Validate decimals/units.
- Handle feed failure/revert behavior.
- Account for sequencer status where relevant.
- Consider manipulation, liquidity, latency, and update frequency.

Use a mechanism appropriate to the protocol: trusted feeds, TWAPs, multiple sources, signed prices, or other validated designs.

For swaps, liquidations, lending, or pricing:
- Enforce slippage/deadline bounds where applicable.
- Analyze flash-loan and transaction-order attacks.
- Check all economic edge cases and insolvency conditions.

---

## 6. Upgradeability & Storage

When upgradeable:
- Protect initialization.
- Verify implementation/admin authority.
- Review storage layout on every upgrade.
- Preserve storage ordering and types.
- Check proxy/implementation assumptions.
- Test upgrade and post-upgrade invariants.
- Review upgrade authorization as a critical trust boundary.

Never treat upgradeability as a deployment detail; it is part of the security model.

---

## 7. Foundry Testing Standard

Target **>=95% meaningful line/statement coverage** for production contracts.

Coverage is a quality gate, **not proof of security**. Critical logic must also have targeted, fuzz, and invariant tests.

### Required Test Categories

#### Unit Tests
Cover:
- Happy paths
- Every important state transition
- Boundary values
- Zero values/addresses
- Authorization failures
- Invalid states
- Reverts and custom errors
- Events
- ETH/token flows

#### Fuzz Tests
Fuzz:
- Amounts
- IDs
- Addresses
- Fees/rates
- Deadlines
- Array lengths where relevant
- State-dependent inputs

Reject invalid assumptions explicitly with `vm.assume()` only when necessary and justified.

#### Invariant Tests
For critical systems, test properties such as:
- Solvency
- Conservation of assets
- Accounting reconciliation
- Access-control invariants
- Supply/balance invariants
- No impossible states
- Monotonic counters/nonces where required

#### Adversarial Tests
Attempt:
- Reentrancy
- Unauthorized calls
- Replay
- Front-running/order dependence
- Oracle manipulation
- Flash-loan-assisted attacks
- Malicious token behavior
- DoS/griefing
- Boundary/rounding exploitation
- Unexpected external-call failures

#### Fork Tests
Use forked networks when real protocol integrations, oracle behavior, liquidity, or deployed contract state materially affect correctness.

---

## 8. Foundry Test Patterns

Use current Foundry cheatcodes and idiomatic patterns.

```solidity
function testRevertWhenUnauthorized() public {
    vm.prank(attacker);
    vm.expectRevert();
    target.adminFunction();
}

function testFuzzDeposit(uint256 amount) public {
    vm.assume(amount > 0 && amount <= MAX_DEPOSIT);

    vm.deal(user, amount);
    vm.prank(user);
    target.deposit{value: amount}();

    assertEq(target.balanceOf(user), amount);
}
```

For impersonation use `vm.prank()` / `vm.startPrank()`.

For funding test accounts use `vm.deal()` or token minting/storage setup as appropriate.

For events use `vm.expectEmit()` with the correct indexed/non-indexed fields.

For invariants, use Foundry invariant tests and a dedicated handler/state-machine design for complex protocols.

---

## 9. Required Verification Commands

At minimum, run:

```bash
forge fmt --check
forge build
forge test
forge test -vvvv
forge test --gas-report
forge coverage
forge snapshot
```

When a gas baseline is tracked:

```bash
forge snapshot --check
```

Use targeted commands during development:

```bash
forge test --match-test <testName>
forge test --match-path <path>
```

Run fork tests when integration behavior requires real chain state.

Do not mark work complete if the build or relevant tests fail.

---

## 10. Gas Optimization

Optimize only after correctness/security is established.

Prefer:
- Fewer unnecessary storage reads/writes
- Appropriate storage packing when it does not hurt readability or upgrade safety
- `calldata` for read-only external array/struct parameters when appropriate
- Caching repeated storage reads in memory
- Custom errors
- Unnecessary writes avoided
- Efficient data structures
- Bounded loops
- Safe use of immutables/constants

Use `unchecked` only with proven bounds.

Measure changes using gas reports/snapshots. Never optimize based on intuition alone.

---

## 11. Code Style

- 2-space indentation.
- `camelCase` for functions/variables.
- `PascalCase` for contracts, libraries, structs, enums, and events.
- `UPPER_SNAKE_CASE` for constants/immutables where appropriate.
- SPDX identifier on source files.
- Consistent pinned pragma.
- Max line length: 120 characters where practical.
- Clear ordering of declarations and functions.
- One logical responsibility per function where practical.
- Prefer explicitness over cleverness.
- Keep security-critical logic easy to audit.

---

## 12. Audit Review Procedure

When reviewing existing code:

1. Map every external/public entry point.
2. Identify privileged functions and state-changing paths.
3. Trace every external call.
4. Trace every asset/accounting flow.
5. Check invariants against each state transition.
6. Review arithmetic, rounding, units, and bounds.
7. Review signatures/nonces/deadlines.
8. Review oracle assumptions.
9. Review upgrade/storage assumptions.
10. Check DoS and gas-griefing paths.
11. Compare implementation against tests and intended behavior.
12. Attempt exploit construction, not just pattern matching.
13. Report findings with severity, impact, root cause, exploit scenario, and remediation.

Never declare a contract "secure" solely because it uses OpenZeppelin, passes tests, or has high coverage.

---

## 13. Definition of Done

A contract/change is not complete until:

- Threat model is understood.
- Critical invariants are identified.
- Privileged roles are explicit.
- External calls are reviewed.
- Token/ETH handling is safe.
- Oracle/signature/upgrade risks are addressed where applicable.
- Unit tests cover important behavior and failure paths.
- Fuzz tests cover critical input-dependent logic.
- Invariant tests cover critical protocol properties.
- Relevant adversarial cases are tested.
- `forge build` passes.
- `forge test` passes.
- Meaningful coverage is >=95% unless an explicit project exception is documented.
- Gas impact has been measured for performance-sensitive paths.
- No unexplained `unchecked`, assembly, delegatecall, or low-level call remains.
- The final diff has received an audit-style security review.

---

## 14. Project-Specific Rules

If the project provides protocol-specific requirements, they are additive to this skill.

For NebulaVerifiableAI or similar job/payment contracts:
- Protect payment and settlement paths against reentrancy where applicable.
- Validate job IDs, model IDs, provider/verifier authorization, amounts, deadlines, and status transitions.
- Ensure job state cannot be completed, verified, paid, or refunded more than once.
- Reconcile recorded balances with actual token/ETH movements.
- Use safe token operations.
- Emit auditable events for job creation, verification, settlement, cancellation, and administrative changes.
- Test malicious providers, verifiers, callers, tokens, repeated calls, invalid state transitions, and failed payment paths.

Never add project-specific shortcuts that weaken the general security requirements above.
