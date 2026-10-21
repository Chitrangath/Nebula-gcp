# NET-002 Arbiscan verification queue diagnosis

Date: 2026-09-25
Scope: Arbitrum Sepolia (`421614`) deployment at
`0xbD0A2f65ae2C67A313d2883cAed5029A3275a599`

Resolution: the owner used Arbiscan's Standard JSON browser workflow. Arbiscan
subsequently published the verified source, ABI, contract name, compiler
metadata, and 15-file source bundle. This note is retained as recovery history.

## Conclusion

At diagnosis time, the evidence pointed to an Arbiscan/Etherscan
verification-job queue or result-indexing problem, not a failed deployment and
not a known Solidity build mismatch.

This is an inference from the combined evidence:

- the deployment and follow-up configuration transactions succeeded;
- the deployed runtime and contract getters have already been independently
  checked;
- Etherscan had accepted four source-verification submissions and returned
  GUIDs, but every GUID remained `Pending in queue` rather than returning a
  compiler or bytecode mismatch;
- the address-level Etherscan source endpoint returned no source; and
- Sourcify reported `exact_match` for the same address and source/build data.

Etherscan documents verification as an asynchronous submission: acceptance
returns a GUID, and the GUID must then be polled for the result. Therefore an
`OK` submission response does not itself mean the source was verified.
[Etherscan: Verify Solidity Source Code](https://docs.etherscan.io/api-reference/endpoint/verifysourcecode)
[Etherscan: Check Source Code Verification Status](https://docs.etherscan.io/api-reference/endpoint/checkverifystatus)

Sourcify defines `exact_match` as byte-for-byte correspondence under the
submitted compiler settings, including matching Solidity metadata/source
integrity hashes, subject to its documented handling of libraries and
immutables. That is strong independent evidence that the source and build
inputs are correct, although it does not force Arbiscan to publish the source.
[Sourcify: Exact Match vs Match](https://docs.sourcify.dev/docs/exact-match-vs-match/)

Neither Etherscan nor Arbiscan's public documentation provides a processing
deadline for a pending GUID or a way for a user to clear a stuck queue item.
Consequently the exact internal failure cannot be proved from outside the
explorer.

## What this does and does not affect

Source verification is an explorer-side, off-chain publication operation. It
does not change the deployed bytecode or contract state. Retrying verification,
using Arbiscan's browser verifier, or opening a support ticket requires no
contract transaction and no redeployment.

The contract should **not** be redeployed. The current deployment is live and
matches the intended configuration; a replacement would create an unnecessary
second canonical address and would not cure an explorer queue problem.

Arbiscan showing a successful deployment transaction or executable contract
does not by itself mean the source is verified. Successful explorer source
verification is established when the address's Contract/Code page publishes
the source and identifies it as verified. Arbiscan documents **Verify and
Publish** as the workflow that recompiles the submitted source and matches it
to the deployed code.
[Arbiscan: Verifying Contracts](https://info.arbiscan.io/how-to-verify-contracts/)

## Recommended recovery order

At diagnosis time there were already four pending Etherscan GUIDs. The recovery
avoided creating further identical API submissions at short intervals because
they add ambiguity without improving the deployed contract.

### 1. Check the existing result once

Poll the most recent GUID once using the existing explorer API key. Foundry's
documented verification flow uses `forge verify-check`, while
`forge verify-contract --watch` performs polling after a new submission.
[Foundry: Deploying and verifying](https://getfoundry.sh/forge/deploying/)

Do not print, paste into chat, or commit the explorer API key. If the result is
still `Pending in queue`, proceed to the manual route rather than submitting a
fifth identical API job.

### 2. Generate the exact Standard JSON input locally

From `contracts/`, with the repository at source commit
`33006ebf6563916eb5d55b974042ddf1788a7be3`, generate the compiler input:

```bash
CONSTRUCTOR_ARGS=$(cast abi-encode \
  'constructor(address)' \
  0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d)
forge verify-contract \
  --chain 421614 \
  --compiler-version 0.8.20+commit.a1b79de6 \
  --num-of-optimizations 200 \
  --via-ir \
  --evm-version shanghai \
  --constructor-args "$CONSTRUCTOR_ARGS" \
  --show-standard-json-input \
  0xbD0A2f65ae2C67A313d2883cAed5029A3275a599 \
  src/NebulaVerifiableAI.sol:NebulaVerifiableAI \
  > /tmp/nebula-arb-sepolia-standard-input.json
```

Foundry explicitly documents `--show-standard-json-input` as compiler input
that can be submitted manually in the explorer browser.
[Foundry: `forge verify-contract`](https://getfoundry.sh/forge/reference/verify-contract/)

Before uploading, inspect the JSON and confirm:

- Solidity compiler `v0.8.20+commit.a1b79de6`;
- optimizer enabled with `200` runs;
- `viaIR: true`;
- EVM version `shanghai`;
- contract identifier
  `src/NebulaVerifiableAI.sol:NebulaVerifiableAI`; and
- constructor argument is the 32-byte ABI encoding of Circle test USDC
  `0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d`.

The generated JSON contains source code and compiler settings, not a private
key. Still, do not add it to Git unless the project deliberately decides to
retain it as an audited artifact.

### 3. Submit once through Arbiscan's browser

Open the deployed address on Arbiscan, select **Contract** -> **Verify and
Publish**, and choose **Solidity (Standard-Json-Input)**. Upload the generated
JSON and select the exact Solidity compiler version above. Supply the encoded
constructor argument if the form requests it separately.

Standard JSON is the correct browser route because Arbiscan states that
advanced compiler settings such as `viaIR: true` are available through the
Standard-Json-Input method.
[Arbiscan: Verifying Contracts](https://info.arbiscan.io/how-to-verify-contracts/)

This form must never receive:

- the deployer private key or seed phrase;
- an RPC URL containing a credential;
- the explorer API key; or
- the ignored Foundry broadcast journal.

If the manual submission produces a concrete compiler or bytecode error, save
the exact error text and stop; it is more actionable than another blind retry.
If it also remains queued, escalate to explorer support.

### 4. Escalate the stuck jobs to official support

Contact the official explorer support channel and include only public or
non-secret diagnostic material:

- network: Arbitrum Sepolia, chain ID `421614`;
- contract: `0xbD0A2f65ae2C67A313d2883cAed5029A3275a599`;
- deployment transaction:
  `0xaf2a0073e7cd59bc5ab503c19157b55bbf47fe37dc8a500c009c0e4f995ea0a0`;
- all verification GUIDs and their submission timestamps;
- the unchanged `Pending in queue` responses;
- compiler `v0.8.20+commit.a1b79de6`, optimizer `200`, `viaIR: true`, and
  EVM `shanghai`;
- the contract identifier and encoded constructor argument above; and
- the Sourcify job/result showing `exact_match`.

Ask them to inspect or clear the stuck verification jobs and refresh the
address-level source index. Etherscan's contact guidance explicitly warns never
to send private keys or passwords and asks users not to spam duplicate support
requests.
[Etherscan: Contact Us](https://etherscan.io/contactus)

## Safe owner actions

The owner can safely perform the manual Standard JSON submission and submit the
support request. Neither action changes contract state or spends testnet ETH.
The owner does not need to sign a blockchain transaction.

The owner should not:

- redeploy the contract;
- send any corrective on-chain transaction;
- publish `.env`, private keys, RPC credentials, or explorer keys;
- alter source or build settings merely to make a verifier accept them; or
- repeatedly submit identical API verification jobs.

## Closure criterion

The closure criterion was met: Arbiscan's address page and address-level source
API expose the verified Solidity source, compiler version, and ABI. Sourcify's
`exact_match` remains independent corroborating evidence.
