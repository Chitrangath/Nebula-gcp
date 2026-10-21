# Deployment Configuration Threat Model

Status: DPL-001 implementation record
Scope: pre-broadcast configuration validation only
Out of scope: deployment transactions, contract configuration transactions,
ownership transfer, testnet broadcasting, and secret custody

## Security objective

Every supported deployment entry point must validate the same public
configuration before `vm.startBroadcast`. Invalid configuration must fail
without deploying or calling `NebulaVerifiableAI`.

The validator's interface contains only:

- explicit network mode
- USDC contract address
- intended contract owner
- trusted Nebula backend verifier
- job price in USDC base units
- maximum job amount in USDC base units

It deliberately contains no private key, seed phrase, RPC credential, worker
signer, AI user, or GPU provider payout address. The absence of worker/provider
identity fields prevents a later script from accidentally treating those roles
as the privileged verifier.

## Actors and trust boundaries

| Actor/dependency | Trust assumption | Threat at this seam | Control |
|---|---|---|---|
| Deployment operator | Selects intended public values | Typo, stale value, or wrong mode | Precise validation before broadcast |
| RPC/selected chain | Supplies `block.chainid` and account state | Wrong network or endpoint | Mode-to-chain-ID equality |
| Configured USDC | External contract called for metadata | EOA, absent code, revert, malformed token, wrong units | Code check, guarded `decimals()`, exact 6 decimals |
| Contract owner | Holds administrative authority after deployment | Zero/burned ownership at creation | Nonzero validation |
| Backend verifier | Assigns providers, submits proof, settles escrow | Missing or confused privileged identity | Nonzero validation and narrow config field |

## Assets and critical invariants

- No transaction is broadcast before validation succeeds.
- Local mode can run only on Anvil's configured chain ID `31337`.
- Arbitrum Sepolia mode can run only on chain ID `421614`.
- The configured USDC address is nonzero, has runtime code, and reports exactly
  six decimals before amounts are interpreted as USDC base units.
- Owner and verifier addresses are nonzero.
- `jobPrice` is positive and does not exceed `maxJobAmount`.
- Secret material cannot cross this interface or be emitted by it.
- This validation does not weaken the contract's authorization, escrow,
  settlement, pull-payment, replay, or solvency invariants.

## Threat analysis

### Wrong-chain broadcast

An operator could select a public RPC while believing it is local, or select a
Sepolia configuration against another chain. `NetworkMode` has an explicit
`Unspecified` zero value, and both supported modes bind to an exact chain ID.
This also prevents `Local` from becoming a general-purpose bypass on a public
chain.

### Invalid or malicious token address

A zero address or EOA would create a deployment whose escrow dependency cannot
work. Both are rejected. A contract can revert while returning token metadata;
the validator converts that failure into a precise error. Any token reporting a
decimal count other than six is rejected so price/cap units cannot silently
change.

The metadata check cannot prove that a token fully conforms to ERC-20 or is the
official Circle deployment. DPL-002 must retain this validator, and public
deployment preflight must separately compare the address with Circle's current
official Arbitrum Sepolia address and inspect runtime code.

### Privileged-role confusion

Zero owner or verifier values could make administration or job progression
unavailable. They are rejected. Equality between owner and verifier is not
rejected because the roadmap explicitly permits deployer/owner consolidation
for a testnet rehearsal and the contract initially assigns both roles to the
deployer. Production-grade role separation remains an operator and deployment
script responsibility. Worker signer and provider payout identities do not
exist in this interface.

### Invalid economic bounds

A zero price creates a meaningless escrow path. A price above the cap would
conflict with the contract's setters and make deployment configuration
unexecutable. Both are rejected together through one price/cap invariant.

### External call behavior

Validation performs one checked low-level `staticcall` to the configured USDC
for `decimals()`. It rejects a reverted call, return data whose length is not
exactly 32 bytes, decoded values outside the `uint8` range, and values other
than six. The call forwards available gas, but it occurs before broadcast and
public deployment separately binds the address to official Circle USDC. It
makes no token transfer, approval, state write, delegatecall, or value transfer.
Reentrancy cannot mutate validator state because `staticcall` is read-only and
the library has no state.

## Residual risks and later-ticket obligations

- A malicious six-decimal contract can pass metadata validation. DPL-002 and
  NET-001 must bind public deployment to the official, freshly verified Circle
  address; local tests use an intentional mock.
- A correct chain ID does not prove RPC honesty or finality. NET-001/NET-003
  must validate code, receipts, confirmations, logs, and getter readbacks.
- The validator cannot prove custody or role ownership. HUM-001 remains an
  owner-controlled identity and custody gate.
- The price/cap pair is valid but may still be commercially unintended. The
  deployment preview must display both public values for explicit owner review.
- DPL-002 must call this validator before `vm.startBroadcast`; its tests must
  prove the ordering through observable no-broadcast behavior.

## Test evidence required by DPL-001

Tests exercise the public harness seam and cover:

- valid local and Arbitrum Sepolia configurations
- unspecified mode and mode/chain mismatch
- zero USDC, address without code, reverting metadata, and wrong decimals
- zero owner and zero verifier
- zero price and price above maximum

No production contract, ABI, storage layout, or deployed behavior changes in
this ticket.
