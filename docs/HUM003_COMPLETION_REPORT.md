# HUM-003 Completion Report

Date: 2026-09-25
Starting commit: `b53bc61`
State: **DONE**

## Outcome

The owner rotated the Alchemy API key that had been exposed in chat, supplied a
replacement Arbitrum Sepolia HTTPS endpoint through hidden terminal input, and
approved its placement in ignored local configuration. An explorer verification
key was also supplied through hidden input for later NET-002 source verification.

No credential value, endpoint, wallet address, or balance is reproduced in this
report. No transaction was signed or broadcast.

## Credential placement

- The replacement RPC endpoint is stored in ignored `contracts/.env` and
  `backend/.env` as `ARBITRUM_SEPOLIA_RPC`.
- The explorer key is stored only in ignored `contracts/.env` as
  `ETHERSCAN_API_KEY`.
- Both files have filesystem mode `600`.
- The contracts and backend RPC values match exactly.
- The old exposed Alchemy key was not copied, tested, or written by the agent.

IP restrictions remain deferred until hosted infrastructure provides stable
egress. The owner confirmed the replacement app is scoped to Arbitrum Sepolia
and reviewed the usage controls available on the account.

## Machine-derived validation

Local structural checks and an independent read-only live check reported:

```text
PASS: contracts and backend secret files are ignored with mode 600
PASS: required HUM-003 evidence fields are unique
PASS: contracts/backend RPC credentials match
PASS: rotated endpoint has expected Alchemy Arbitrum Sepolia format
PASS: owner approval and chain/provider metadata recorded
PASS: rotated RPC authenticated successfully
PASS: live chain ID is 421614
PASS: positive block number and client response returned
```

The explorer key is present but cannot be meaningfully validated until a
contract exists to verify. NET-002 must test it without printing it and must
repair verification on the existing deployment rather than redeploying.

## Integration preservation

After the ignored environment changes, the complete local Golden E2E matrix was
rerun against PostgreSQL and disposable Anvil contracts:

```text
4 passed in 6.91s
```

The valid settlement, invalid-proof refund, paused timeout refund, and
refund/settlement-race journeys remain connected and green.

## Files in this ticket

- `scripts/hum003_rpc_credentials_wizard.sh`
- `docs/HUM003_COMPLETION_REPORT.md`
- `docs/POST_PHASE3_SUB_TICKETS.md`

Ignored `contracts/.env` and `backend/.env` contain owner-controlled local
configuration and must never be committed.

## Skill usage

All 14 skills documented by `AGENTS.md` were considered.

Applied:

1. `wizard`: collected credentials through hidden terminal input, enforced
   rotation and confirmation gates, validated the RPC, and persisted only to
   ignored mode-`600` files.

Not applied: `solidity-foundry-security`, `tdd`, `domain-modeling`,
`code-review`, `diagnosing-bugs`, `research`, `codebase-design`,
`grill-with-docs`, `improve-codebase-architecture`, `handoff`, `ask-matt`,
`setup-matt-pocock-skills`, and `teach`; this ticket changed no application or
contract behavior. Current Alchemy key-management instructions were checked
directly against official documentation as part of the credential workflow.

## Next ticket

NET-001 is now `READY`. It is a joint no-broadcast deployment preflight: produce
the exact source state, public role map, balances, transaction sequence, gas
estimate, artifact hashes, rehearsal evidence, and ownership-transfer statement
for explicit owner authorization. HUM-003 itself grants no broadcast authority.
