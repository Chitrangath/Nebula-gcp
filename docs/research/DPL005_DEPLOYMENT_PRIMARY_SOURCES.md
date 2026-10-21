# DPL-005 Arbitrum Sepolia Deployment Sources

Retrieved: 2026-09-09 (UTC)

Scope: primary-source facts needed to write and execute the Nebula Arbitrum
Sepolia deployment runbook. This note is informational; it does not authorize a
broadcast or contain wallet secrets.

## Network identity and endpoints

- Arbitrum Sepolia's chain ID is `421614`.
- Offchain Labs lists `https://sepolia-rollup.arbitrum.io/rpc` as the public
  general-purpose RPC endpoint.
- The official explorers listed for the network are Arbiscan at
  `https://sepolia.arbiscan.io/` and Blockscout at
  `https://arbitrum-sepolia.blockscout.com/`.
- The public RPC has no WebSocket support. The documentation also describes
  Arbitrum public RPC service as best effort, without uptime, latency, or
  rate-limit guarantees; production-like automation should therefore use a
  reputable authenticated RPC provider or a fallback rather than assume the
  public endpoint has an SLA.

Source: [Offchain Labs, Arbitrum chain information](https://docs.arbitrum.io/for-devs/dev-tools-and-resources/chain-info)

## Testnet funds and canonical test USDC

- Circle lists the Arbitrum Sepolia test USDC contract as
  `0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d`.
- Circle states that testnet USDC has no financial value and is not backed by
  real US dollars.
- Circle's EVM transfer quickstart treats USDC as a six-decimal token.
- Circle's faucet supports Arbitrum Sepolia and can dispense test USDC:
  `https://faucet.circle.com/`.
- The deployment wallet also needs Arbitrum Sepolia ETH for gas. Offchain Labs'
  chain-information page maintains a faucet list; faucet availability and
  eligibility are third-party operational details and must be checked by the
  human operator at execution time.

Sources: [Circle, USDC contract addresses](https://developers.circle.com/stablecoins/usdc-contract-addresses),
[Circle, transfer USDC on EVM chains](https://developers.circle.com/stablecoins/quickstarts/transfer-usdc-evm),
[Circle testnet faucet](https://faucet.circle.com/), and
[Offchain Labs faucet list](https://docs.arbitrum.io/for-devs/dev-tools-and-resources/chain-info#faucet-list).

## Foundry simulation and broadcast boundary

- A Forge script invocation without `--broadcast` is a dry run/simulation.
- Adding `--broadcast` publishes the script's transactions to the selected
  network. Foundry documents this flag as an intentional safety boundary.
- Foundry's documented testnet flow is: first run the script with its RPC URL
  to simulate, then repeat with signing credentials plus `--broadcast`; add
  `--verify` only when source verification is also intended.
- The RPC chain ID, deployment configuration, signer address, signer balance,
  transaction preview, and constructor arguments should therefore be checked
  before the command containing `--broadcast` is approved.
- Signing material should be supplied through an operator-controlled Foundry
  signer mechanism or secret environment at execution time, never committed to
  the repository or copied into a public manifest.

Sources: [Foundry, deploying and verifying](https://getfoundry.sh/forge/deploying) and
[Foundry, orchestrating scripts with config](https://getfoundry.sh/guides/scripting-with-config/).

## Source verification

- Foundry supports verification during deployment with `--verify`, or later
  with `forge verify-contract`.
- A later verification requires the deployed address and contract identifier;
  it may also require ABI-encoded constructor arguments, the exact compiler
  version/profile, optimizer runs, linked libraries, and the non-mainnet chain
  ID. Verification inputs must match the deployment build.
- `forge verify-contract --watch` waits for the provider's result and is the
  documented way to avoid treating submission as successful verification.
- Foundry supports Etherscan-compatible, Sourcify, and Blockscout verification
  providers. For Etherscan-compatible verification, current Foundry guidance
  says an Etherscan API key is required. Blockscout can instead be selected
  explicitly with its verifier URL where supported.
- The public deployment record should distinguish `broadcast succeeded` from
  `source verified`: a transaction receipt proves deployment, while successful
  explorer verification is a separate outcome.

Sources: [Foundry, deploying and verifying](https://getfoundry.sh/forge/deploying),
[Foundry, `forge verify-contract`](https://getfoundry.sh/forge/reference/verify-contract/), and
[Foundry verifier options](https://www.getfoundry.sh/reference/common/verifier-options).

## Runbook implications

1. Pin chain ID `421614` and Circle USDC
   `0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d`; abort on mismatch.
2. Confirm the RPC reports chain ID `421614`, the USDC address has contract
   code, and its `decimals()` result is `6` before simulation or broadcast.
3. Complete the existing build, tests, artifact-consistency checks, and Forge
   dry run before seeking owner approval for the broadcast command.
4. Have the human operator fund the intended signer with test ETH and obtain
   test USDC only if the post-deployment smoke journey needs it.
5. Broadcast once, preserve transaction hashes/receipts, verify runtime code
   and constructor state on-chain, then perform source verification using the
   exact build settings.
6. Validate the resulting public manifest with the DPL-004 validator before it
   becomes an input to backend or frontend configuration.

## Uncertainties and execution-time checks

- Public RPC health, faucet availability, rate limits, and API-key policies are
  operationally mutable; re-check them immediately before deployment.
- Arbiscan is an official explorer link in Offchain Labs documentation, but
  verifier authentication is governed by the current Etherscan-compatible API
  policy. Confirm the installed Forge version's supported verifier flags and a
  valid API key before relying on automatic Arbiscan verification.
- Circle's address page is the authority for test USDC and can change across
  testnet migrations. Re-open it and compare the address immediately before
  broadcast; do not rely solely on this dated research note.
- This research does not establish finality requirements for application
  indexing. Receipt confirmation, Arbitrum L2 inclusion, parent-chain posting,
  and parent-chain finality are different states; the deployment runbook must
  state which level is required for each gate.
