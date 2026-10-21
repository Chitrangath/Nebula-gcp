# NET-001 Arbitrum Sepolia Deployment Preflight

Date: 2026-09-25
Contract source commit: `33006ebf6563916eb5d55b974042ddf1788a7be3`
State: **DONE WITH PROCESS EXCEPTIONS — deployed values match the preview**

## Scope and stop condition

This is the exact public no-broadcast preview for owner review. The successful
command omitted `--broadcast`. Any source, nonce, role, token, price, cap,
transaction-sequence, or chain change voids this preview and requires a new
simulation and authorization.

## Approved public configuration

| Field | Value |
|---|---|
| Network | Arbitrum Sepolia |
| Chain ID | `421614` |
| Deployer | `0xf186F4958A1bf6843148Ed9aC737FEb35cCCF5dc` |
| Contract owner | `0xf186F4958A1bf6843148Ed9aC737FEb35cCCF5dc` |
| Backend verifier | `0x3816323AB50dbB47fa175f1A49f26FdBE143B567` |
| AI user | `0xed8cc7462Fe5D0A03409e886ADc6F6EA09e76FA0` |
| Provider payout | `0x97ecf1D8F8f265d108e9feC55776006074060D29` |
| Worker signer | `0x5F320995cbD939B12080D9b149A8D0Db17342ac5` |
| Circle test USDC | `0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d` |
| Job price | `50,000` base units (`0.05` test USDC) |
| Maximum job amount | `10,000,000` base units (`10` test USDC) |
| Source verification requested | Yes, after a successful deployment receipt |

The deployer and owner are intentionally the same testnet wallet. Verifier, AI
user, provider, and worker signer are nonzero and pairwise distinct from each
other and from the deployer/owner. The worker signer remains unfunded.

## Canonical artifact identity

```text
ABI SHA-256:              57a205796f5ea3e9189e281af31dcdc337386075f1ae8060a0d34fe3c5aaf0e9
Runtime template SHA-256: 54b4029baa8f1487adda2c3f7a676b54524ec8a591b61f843e63d349aa58faef
Compiler:                  0.8.20+commit.a1b79de6
Optimizer:                 enabled, 200 runs
viaIR / EVM:               true / shanghai
```

Artifact sync, `forge fmt --check`, build, 18 deployment-configuration tests,
9 deployment-script tests, and 15 deployment manifest/artifact tests passed.

## Live funding evidence at preview time

```text
Deployer/owner ETH: 0.071150743465032400
Backend verifier ETH: 0.000694601116426000
AI-user ETH: 0.010000000000000000
Provider ETH: 0.010498465237120000
Worker-signer ETH: 0
AI-user test USDC: 60.000000
```

Balances must be rechecked immediately before broadcast. The verifier balance is
adequate for later testnet operations at the observed fee level but is the
smallest gas-paying balance and must remain a stop condition if fees or the
planned journey materially change.

## Exact simulation and transaction sequence

Correct no-broadcast command:

```text
forge script script/Deploy.s.sol:Deploy --rpc-url "$ARBITRUM_SEPOLIA_RPC" --chain-id 421614 -vvvv
```

The first wizard attempt omitted the explicit RPC option, so Foundry used an
unforked local EVM and correctly raised `MissingUSDCCode`. Adding only the
explicit RPC option loaded Arbitrum Sepolia state and made the same validation
and simulation pass. The corrected command was used for the successful preview.

Current deployer nonce: `3`. Predicted contract address:
`0xbD0A2f65ae2C67A313d2883cAed5029A3275a599`. A read-only code check returned
`0x`, confirming no contract currently exists there.

The dry run contains exactly two transactions and zero receipts:

1. Nonce `3`: CREATE `NebulaVerifiableAI`, constructor argument Circle test
   USDC, gas limit `1,859,391`, zero ETH value.
2. Nonce `4`: call `setVerifier(0x3816323AB50dbB47fa175f1A49f26FdBE143B567)`
   on the predicted contract, gas limit `32,254`, zero ETH value.

No ownership-transfer transaction is needed because owner equals deployer. No
price/cap transaction is needed because the approved values equal constructor
defaults. Privileged verifier configuration occurs while the deployer is owner.

Foundry estimate:

```text
Estimated gas price: 0.068156001 gwei
Estimated total gas: 1,891,645
Estimated amount required: 0.000128926958511645 ETH
```

The deployer balance exceeds the estimate. The estimate remains testnet-only and
must be regenerated if nonce, source, network state, or configuration changes.

## Security review and authorization boundary

- `DeploymentConfig.validate()` executes before private-key parsing/broadcast.
- USDC code and six decimals were read from the live chain.
- Deployment is non-upgradeable; no proxy or initializer authority exists.
- The contract uses pull withdrawals and preserves the previously tested
  solvency, role, replay, deadline, and mutually exclusive settlement/refund
  invariants.
- The backend verifier is a privileged trusted role; compromise can assign,
  submit, and settle jobs, but cannot directly withdraw another recipient's
  credited balance.
- Raw Foundry dry-run/cache files remain ignored and are not canonical evidence.
- Private keys, RPC credentials, explorer credentials, and signed payloads are
  absent from this report and must never be committed.
- A successful L2 receipt is required before any manifest/runtime update.
- Source verification is a separate post-receipt action. Verification failure
  must be repaired on the existing deployment, not by redeploying.

## Required owner decision

The owner authorized commit `33006ebf6563916eb5d55b974042ddf1788a7be3`,
chain `421614`, predicted address, the documented two-transaction sequence,
job price/cap, shared deployer/owner decision, and requested source
verification. The final live recheck matched this preview.

Retrospective two-axis review found that the authorization message did not
explicitly repeat the deployer, owner, verifier, USDC, or numeric gas estimate,
despite the runbook requiring every field in the authorization itself. It also
found that these uncommitted documentation files made the overall working tree
dirty even though the complete contract tree exactly matched the authorized
source commit. These are process deviations, not on-chain configuration
mismatches. They cannot be undone by redeployment and are recorded in
`docs/NET002_DEPLOYMENT_REPORT.md`.
