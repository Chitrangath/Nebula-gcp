# NET-002 Arbitrum Sepolia Deployment Report

Date: 2026-09-25
Source commit: `33006ebf6563916eb5d55b974042ddf1788a7be3`
State: **DONE — deployment, source verification, and manifest validation pass**

## Broadcast result

The owner-authorized two-transaction sequence was broadcast once to Arbitrum
Sepolia chain `421614`. Both L2 receipts succeeded:

| Operation | Nonce | Transaction | Block |
|---|---:|---|---:|
| Deploy `NebulaVerifiableAI` | `3` | `0xaf2a0073e7cd59bc5ab503c19157b55bbf47fe37dc8a500c009c0e4f995ea0a0` | `312679343` |
| `setVerifier(address)` | `4` | `0xeea8ac1ef3d1a3defa8abc1f4f0fb1c79cdb932b02f8812a736240989053121c` | `312679348` |

Contract address:
`0xbD0A2f65ae2C67A313d2883cAed5029A3275a599`

Deployment block timestamp: `2026-09-25T19:28:14Z`.

The ignored Foundry broadcast/cache journals are operational evidence only and
must not be committed or used as the public manifest.

## Independent on-chain readback

| Getter/evidence | Observed value |
|---|---|
| `token()` | `0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d` |
| `owner()` | `0xf186F4958A1bf6843148Ed9aC737FEb35cCCF5dc` |
| `verifier()` | `0x3816323AB50dbB47fa175f1A49f26FdBE143B567` |
| `jobPrice()` | `50000` |
| `maxJobAmount()` | `10000000` |
| `paused()` | `false` |
| `totalEscrowed()` | `0` |
| `totalPendingWithdrawals()` | `0` |
| `invariant_solvency()` | `true` |
| On-chain runtime SHA-256 | `c3a04e93e7efcd2010b6a5bdbb24ff03d60936363bb37cd24d7b899d2326ec4a` |

The configured token, roles, economic bounds, pause state, accounting totals,
and solvency invariant all match the authorized preview. The deployed runtime
is nonempty. The on-chain runtime hash intentionally differs from the artifact
runtime-template hash because the constructor embeds immutable USDC.

## Source verification status

The exact compiler profile and constructor argument were submitted to the
Etherscan/Arbiscan verifier for the existing deployment:

```text
Compiler: 0.8.20+commit.a1b79de6
Optimizer: enabled, 200 runs
viaIR: true
EVM: shanghai
Constructor USDC: 0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d
Initial verification GUID: wtqwk3vjgqjlv42qlsmivymjdhpnqsit7u3qiyqjgsbl6a2uwy
Replacement verification GUID: tcf3xewqrnqt8ymx44uwgzmcegfw5bkahmsbmstindqbwwj4ct
```

Arbiscan accepted the initial and replacement submissions (`OK`) but initially
left them `Pending in queue`. Two attempted Sourcify submissions were also
redirected to Etherscan because Foundry auto-loaded `ETHERSCAN_API_KEY` from the
project `.env`; those identical submissions are pending as well and created no
on-chain transaction. Explicitly overriding that variable with an empty value
then submitted the same source to Sourcify. Sourcify job
`3576204f-8e59-4c56-87ac-bdfd7284379d` completed with `exact_match`.

The independent exact match proved the submitted build metadata and source
matched the deployed bytecode. The owner then completed the manual Standard
JSON workflow. Arbiscan's address-level API now returns contract name
`NebulaVerifiableAI`, compiler `v0.8.20+commit.a1b79de6`, optimizer enabled with
`200` runs, EVM `shanghai`, a nonempty source bundle, ABI, and all 15 source
files. The browser verification page also reports that the address has already
been verified. The canonical manifest is published at
`contracts/deployments/arbitrum-sepolia.json`.

## Verification-script diagnosis

The first combined readback shell stopped after successful calls because
Foundry rendered integer results as `50000 [5e4]` and `10000000 [1e7]`, while
the shell expected bare decimal strings. Isolated reads proved the contract
state was correct. Normalizing each integer to its first output field made the
same deterministic check pass. No contract, transaction, or repository runtime
code changed as a result.

## Security boundary

- No corrective transaction or redeployment was sent.
- No private key, RPC credential, explorer key, signed payload, or raw journal
  is present in this report.
- The public manifest contains only sanitized public deployment evidence.
- NET-003 may begin only from the validated manifest and isolated Sepolia
  runtime configuration described by its ticket.

## Retrospective process exceptions

The mandatory two-axis review identified two deployment-process deviations:

1. The Solidity source, script, tests, Foundry configuration, and dependencies
   exactly matched source commit
   `33006ebf6563916eb5d55b974042ddf1788a7be3`, but uncommitted NET-001
   documentation and its one-off wizard made the repository working tree dirty.
   This violated the runbook's literal clean-tree stop condition.
2. The owner's authorization named the source commit, chain, predicted address,
   documented transaction sequence, job price/cap, shared deployer/owner
   decision, and requested verification. It did not explicitly repeat the
   deployer, owner, verifier, USDC, or numeric gas estimate as runbook section 7
   requires. The earlier NET-001 wording overstated this authorization and has
   been corrected.

The deployed address nevertheless matches the reviewed source, predicted
address, roles, token, price/cap, and transaction sequence; both receipts and
all independent readbacks pass. Because the contract is non-upgradeable and
the on-chain result is correct, neither exception justifies a redeployment or
corrective transaction. The exceptions remain permanent audit evidence.

Two fresh-Anvil rehearsals were completed earlier and are machine-recorded in
`docs/DPL005_COMPLETION_REPORT.md` for ports `8547` and `8548`, each ending in
`SIMULATION COMPLETE`. The public preflight revalidated chain ID, live USDC
code, and six decimals. It did not separately record reopening the official
Arbitrum and Circle source pages immediately before broadcast, so that
runbook evidence remains incomplete and is disclosed here.

## Skill usage

### Discovered skills

`solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`,
`diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`,
`improve-codebase-architecture`, `handoff`, `ask-matt`,
`setup-matt-pocock-skills`, `teach`, and `wizard`.

### Applied skills

1. **solidity-foundry-security**: enforced exact-source and authorization
   checks, live token/role/nonce validation, receipt inspection, independent
   getter/accounting/solvency checks, and the no-redeployment recovery rule.
2. **diagnosing-bugs**: isolated the post-deployment assertion failure and
   proved it was numeric CLI formatting rather than incorrect on-chain state.
3. **wizard**: the one-off NET-001 wizard captured owner-only signing material
   without printing it and enforced the separate no-broadcast authorization
   boundary. It was removed after use because the skill treats one-off wizards
   as ephemeral unless retained as a documented reusable setup path.
4. **code-review**: applied a two-axis standards/spec review to the deployment
   evidence before committing the pending external-verification checkpoint.
5. **research**: used primary Foundry, Etherscan/Arbiscan, and Sourcify sources
   to diagnose the stuck explorer queue and document the safe Standard JSON
   recovery workflow.

### Not applied

- **tdd** and **domain-modeling**: no contract or application behavior was
  implemented or changed during the authorized deployment operation.
- The remaining planning, teaching, routing, refactoring, setup, and
  handoff skills did not match this execution/verification stage.
