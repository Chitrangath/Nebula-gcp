# Arbitrum Sepolia Contract Deployment Runbook

Status: operator procedure; it is not deployment authorization and does not
claim that Nebula is deployed.

This runbook deploys the non-upgradeable `NebulaVerifiableAI` contract through
the reviewed `contracts/script/Deploy.s.sol` entry point. Complete the stages in
order. A successful dry run never authorizes the command containing
`--broadcast`.

## 1. Authority and stop conditions

Only the project owner may:

- select or create wallets and custody signing material;
- accept faucet/provider terms or complete human verification;
- fund wallets, create provider accounts, or approve costs;
- approve the exact public deployment preview;
- authorize `--broadcast`, source publication, or corrective transactions.

An agent may run local tests, inspect public addresses/balances, prepare a dry
run, and validate public artifacts. Never paste a private key, seed phrase,
credential-bearing RPC URL, or explorer key into chat, Git, logs, or a public
manifest.

Stop immediately if any of these is true:

- Git is dirty or the reviewed source commit changed after the preview;
- RPC chain ID is not `421614`;
- Circle's current address differs from the configured USDC address;
- USDC has no runtime code or `decimals()` is not `6`;
- any configured role/address/price/cap differs from the approved summary;
- the deployer lacks test ETH or a nonce changed after preview;
- local tests, dry run, gas estimate, or post-deployment assertions fail;
- explicit owner approval for the exact broadcast is absent or stale.

## 2. Pinned public facts and execution-time recheck

As researched on 2026-09-09:

| Fact | Required value |
|---|---|
| Network | Arbitrum Sepolia |
| Chain ID | `421614` |
| Public HTTP RPC | `https://sepolia-rollup.arbitrum.io/rpc` |
| Explorer | `https://sepolia.arbiscan.io/` |
| Circle test USDC | `0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d` |
| USDC decimals | `6` |

Immediately before preview and again before broadcast, the owner must reopen
the official [Arbitrum chain information](https://docs.arbitrum.io/for-devs/dev-tools-and-resources/chain-info)
and [Circle USDC address list](https://developers.circle.com/stablecoins/usdc-contract-addresses).
The public RPC is best effort and has no WebSocket support. Use a reputable
owner-controlled HTTPS provider for repeated automation when needed. Research
details and sources are recorded in
[`docs/research/DPL005_DEPLOYMENT_PRIMARY_SOURCES.md`](../research/DPL005_DEPLOYMENT_PRIMARY_SOURCES.md).

## 3. Required tools and clean source

From the repository root:

```bash
git status --short
git rev-parse HEAD
forge --version
cast --version
backend/.venv/bin/python --version
```

`git status --short` must be empty for a deployment preview. Record the commit
hash. Do not deploy from an uncommitted tree, because the manifest and explorer
verification must identify exact source.

## 4. Stage 1 local readiness gate

These commands are agent-runnable and contain no public-network broadcast:

```bash
cd contracts
forge fmt --check
forge build
forge test
forge test -vvvv
forge test --gas-report
forge snapshot --check
forge coverage --ir-minimum --report summary

cd ..
backend/.venv/bin/python scripts/sync_contract_artifacts.py --check
backend/.venv/bin/python -m unittest discover -s scripts/tests -p 'test_*.py' -v
backend/.venv/bin/ruff check scripts/validate_deployment_manifest.py scripts/tests
backend/.venv/bin/mypy --strict scripts/validate_deployment_manifest.py scripts/tests
```

For the backend gate, export a local PostgreSQL URL whose database path is
exactly `nebula_test`. Never point this command at development, staging, or
production data. Confirm the target without printing credentials:

```bash
cd backend
source .venv/bin/activate
python - <<'PY'
import os
from sqlalchemy.engine import make_url

url = make_url(os.environ["DATABASE_URL"])
assert url.drivername.startswith("postgresql")
assert url.host in {"localhost", "127.0.0.1"}
assert url.database == "nebula_test"
print("confirmed local PostgreSQL target: nebula_test")
PY
python -m pytest -q -ra
uv run ruff check .
uv run ruff format --check .
deactivate
cd ..
```

Acceptance requires zero failed and zero skipped backend tests. Do not replace
this gate with SQLite or a fake database.

### 4.1 Two fresh-Anvil rehearsals

Use these public default Anvil identities only for local simulation:

```bash
export ANVIL_DEPLOYER_ADDRESS=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
export ANVIL_OWNER_ADDRESS=0x70997970C51812dc3A010C7d01b50e0d17dc79C8
export ANVIL_VERIFIER_ADDRESS=0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC
export ANVIL_AI_USER_ADDRESS=0x90F79bf6EB2c4f870365E785982E1f101E93b906
export ANVIL_PROVIDER_ADDRESS=0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65
export ANVIL_WORKER_SIGNER_ADDRESS=0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc
```

Terminal one:

```bash
cd contracts
anvil --silent --port 8547
```

Terminal two:

```bash
cd contracts
forge script script/Smoke.s.sol:Smoke --rpc-url http://127.0.0.1:8547
```

Require `SIMULATION COMPLETE`, then stop Anvil. Start a new Anvil process on
port `8548`, rerun the same command with port `8548`, require success, and stop
it. Never add `--broadcast` to this local smoke command. Inspect and remove the
generated dry-run directories after recording the result:

```bash
cd ..
find contracts/broadcast/Smoke.s.sol contracts/cache/Smoke.s.sol -type f -print
rm -rf contracts/broadcast/Smoke.s.sol contracts/cache/Smoke.s.sol
git status --short
```

The two explicit removal targets are generated smoke artifacts only. Never use
a broad `rm` target, variable, glob, repository root, or home directory.

## 5. Owner-only identity and secret preparation

Approve public addresses for these roles before creating the preview:

| Role | Separation and funding requirement |
|---|---|
| Deployer | Test ETH; signs deployment/configuration transactions |
| Contract owner | Admin authority; may equal deployer only if explicitly recorded |
| Backend verifier | Distinct from user/provider/worker; test ETH for privileged calls |
| AI user | Distinct browser wallet; test ETH and Circle test USDC |
| GPU provider | Distinct payout wallet; test ETH for withdrawal |
| Worker signer | Distinct node key; no funds and no on-chain authority |

The owner obtains test ETH through a currently listed Arbitrum Sepolia faucet
and test USDC through the [Circle faucet](https://faucet.circle.com/). Confirm
balances and the network on an explorer rather than relying only on wallet UI.

The current deployment script accepts the deployer key through an environment
variable. Until a separately reviewed keystore adapter exists, create a local
file such as `contracts/.env.deploy.sepolia`, never a tracked file:

```bash
cd contracts
umask 077
touch .env.deploy.sepolia
chmod 600 .env.deploy.sepolia
git check-ignore -v .env.deploy.sepolia
```

Stop unless `git check-ignore` identifies the repository rule. Populate the
file locally without sharing its contents. It must define:

```text
ARBITRUM_SEPOLIA_RPC=<secret-or-public HTTPS RPC>
NEBULA_DEPLOYMENT_NETWORK=arbitrum-sepolia
NEBULA_USDC=0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d
NEBULA_DEPLOYER_ADDRESS=<approved public deployer address>
NEBULA_CONTRACT_OWNER=<approved public owner address>
NEBULA_BACKEND_VERIFIER=<approved public backend verifier address>
NEBULA_AI_USER_ADDRESS=<approved public AI-user address>
NEBULA_PROVIDER_ADDRESS=<approved public GPU-provider payout address>
NEBULA_WORKER_SIGNER_ADDRESS=<approved public worker-signer address>
NEBULA_JOB_PRICE=<approved integer in 6-decimal USDC base units>
NEBULA_MAX_JOB_AMOUNT=<approved integer not below job price>
NEBULA_DEPLOYER_PRIVATE_KEY=<owner-custodied testnet deployer key>
ETHERSCAN_API_KEY=<owner-custodied explorer key, if required>
```

Never pass a private key as a literal CLI argument. Load the permission-limited
file only in the deployment shell and clear it when finished:

```bash
set -a
. ./.env.deploy.sepolia
set +a
```

## 6. Public-network preflight and no-broadcast preview

The following reads are safe only after the owner supplies the public values
or loads the ignored environment file:

```bash
test "$(cast chain-id --rpc-url "$ARBITRUM_SEPOLIA_RPC")" = "421614"
test "$(cast code "$NEBULA_USDC" --rpc-url "$ARBITRUM_SEPOLIA_RPC")" != "0x"
test "$(cast call "$NEBULA_USDC" 'decimals()(uint8)' --rpc-url "$ARBITRUM_SEPOLIA_RPC")" = "6"
cast balance "$NEBULA_DEPLOYER_ADDRESS" --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast balance "$NEBULA_BACKEND_VERIFIER" --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast balance "$NEBULA_AI_USER_ADDRESS" --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast balance "$NEBULA_PROVIDER_ADDRESS" --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_USDC" 'balanceOf(address)(uint256)' \
  "$NEBULA_AI_USER_ADDRESS" \
  --rpc-url "$ARBITRUM_SEPOLIA_RPC"
forge script script/Deploy.s.sol:Deploy \
  --rpc-url "$ARBITRUM_SEPOLIA_RPC" \
  --chain-id 421614 \
  -vvvv
```

There is deliberately no `--broadcast` above. Record only public facts:

- clean source commit and artifact hashes;
- chain ID and current authoritative USDC address;
- deployer, intended owner, and verifier public addresses;
- public balances needed for the planned journey;
- ordered transactions, nonces, gas estimate, and testnet-only estimated cost;
- whether ownership transfer occurs;
- local readiness and two-fresh-Anvil results.

The preview transaction sender must equal `NEBULA_DEPLOYER_ADDRESS`. Confirm
that the verifier, AI user, provider, and worker signer are nonzero and
pairwise distinct; they must also differ from the deployer and owner. The owner
may equal the deployer only when that exception is explicitly approved. Treat
zero ETH for any gas-paying role or inadequate AI-user USDC for the planned
smoke journey as a failed preflight.

Inspect `contracts/broadcast/Deploy.s.sol/421614/dry-run/` locally. Do not commit
the journal or treat it as the canonical manifest. If the preview differs from
the approved values, stop and regenerate it after correcting configuration.

## 7. Explicit owner authorization checkpoint

Present the sanitized public preview to the owner. Authorization must identify
the source commit, chain, deployer, owner, verifier, USDC, job price/cap,
transaction sequence, gas estimate, and whether source verification is being
requested. Any changed value, nonce, code, RPC chain, or source commit voids
approval. A request to inspect, simulate, or estimate is not permission to
broadcast.

## 8. Broadcast and receipt capture

Only after explicit approval of the exact preview:

```bash
forge script script/Deploy.s.sol:Deploy \
  --rpc-url "$ARBITRUM_SEPOLIA_RPC" \
  --chain-id 421614 \
  --broadcast \
  --slow \
  -vvvv
```

Do not add `--skip-simulation`. Capture every public transaction hash from the
Foundry journal and obtain its receipt:

```bash
cast receipt <DEPLOYMENT_TRANSACTION_HASH> --rpc-url "$ARBITRUM_SEPOLIA_RPC" --confirmations 1
```

A receipt proves L2 inclusion, not explorer source verification or Ethereum
parent-chain finality. For configuration publication, require a successful L2
receipt plus all getter/code checks below. Record deeper confirmation/finality
separately when the runtime policy requires it.

## 9. Immediate post-deployment verification

Set public shell variables from the successful receipt/journal, then run:

```bash
test "$(cast chain-id --rpc-url "$ARBITRUM_SEPOLIA_RPC")" = "421614"
test "$(cast code "$NEBULA_PAYMENT_CONTRACT" --rpc-url "$ARBITRUM_SEPOLIA_RPC")" != "0x"
cast call "$NEBULA_PAYMENT_CONTRACT" 'token()(address)' --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" 'verifier()(address)' --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" 'owner()(address)' --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" 'jobPrice()(uint256)' --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" 'maxJobAmount()(uint256)' --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" 'paused()(bool)' --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" 'totalEscrowed()(uint256)' --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" 'totalPendingWithdrawals()(uint256)' --rpc-url "$ARBITRUM_SEPOLIA_RPC"
cast call "$NEBULA_PAYMENT_CONTRACT" 'invariant_solvency()(bool)' --rpc-url "$ARBITRUM_SEPOLIA_RPC"
```

Require exact configured token/verifier/owner/price/cap, `paused=false`, both
accounting totals `0`, and solvency `true`. Record the receipt's exact block;
never use deployment block `0` for the event indexer.

The raw artifact runtime-template hash is expected to differ from the actual
on-chain runtime hash because constructor-supplied USDC is immutable. Obtain the
template hash from `backend/app/nebula_artifact.json`; hash decoded bytes from
`cast code` for the on-chain value. Do not hash the ASCII `0x...` string.

## 10. Source verification

Verification is separate from deployment. A failed verification submission is
not a reason to redeploy. For the installed Forge interface:

```bash
CONSTRUCTOR_ARGS=$(cast abi-encode 'constructor(address)' "$NEBULA_USDC")
forge verify-contract \
  "$NEBULA_PAYMENT_CONTRACT" \
  src/NebulaVerifiableAI.sol:NebulaVerifiableAI \
  --chain 421614 \
  --rpc-url "$ARBITRUM_SEPOLIA_RPC" \
  --compiler-version 0.8.20+commit.a1b79de6 \
  --num-of-optimizations 200 \
  --via-ir \
  --evm-version shanghai \
  --constructor-args "$CONSTRUCTOR_ARGS" \
  --verifier etherscan \
  --etherscan-api-key "$ETHERSCAN_API_KEY" \
  --watch
```

Confirm the explorer displays verified source for the existing address. If the
provider changes its API rules, recheck `forge verify-contract --help` and the
current official Foundry verifier documentation; do not guess flags.

## 11. Final public manifest

Create a new JSON document conforming to
`contracts/deployments/deployment-manifest.schema.json` only after receipt,
getter, code, and explorer checks succeed. Populate all twenty public fields
from evidence, including the exact commit, receipt block/time, ABI hash,
runtime-template hash, decoded on-chain code hash, and explorer URL. Never copy
RPC credentials, signing material, raw signed transactions, or secret-file
paths into it.

Validate before committing or configuring another runtime:

```bash
backend/.venv/bin/python scripts/validate_deployment_manifest.py \
  contracts/deployments/arbitrum-sepolia.json
git diff --check
git status --short
```

Only after validation may public values be copied consistently into backend,
frontend, worker, and deployment configuration. `CONTRACT_DEPLOYMENT_BLOCK`
must equal the receipt block.

## 12. Failure recovery

### Dry run or preflight failure

No transaction exists. Correct only the identified public configuration,
source, funding, or RPC issue; rerun the complete local gate and preview; obtain
fresh owner approval.

### Partial or uncertain broadcast

Stop. Preserve the ignored Foundry journal and public transaction hashes.
Inspect receipts, sender nonce, deployed code, and getters before doing
anything else. Never rerun the whole script blindly. `forge script --resume`
skips simulation and is safe only when the chain, source, journal, signer, and
expected nonces are unchanged and the owner explicitly authorizes the exact
remaining transactions.

### Deployment succeeded but source verification failed

Do not redeploy. Verify the existing address using the exact compiler profile,
constructor arguments, and creation transaction. Keep `source_verified=false`
in working notes; the finalized validator will reject publication until source
verification succeeds.

### Wrong immutable USDC or wrong bytecode

The deployment cannot be repaired or upgraded. Mark the address invalid, stop
all runtime configuration, preserve evidence, and seek explicit authorization
for a fresh deployment. Never publish the invalid address as canonical.

### Wrong verifier or owner

Do not send an unreviewed corrective admin transaction. If the current owner is
controlled, prepare the exact `setVerifier` or ownership transaction and obtain
separate owner authorization. If authority is unavailable, abandon the address
and plan a replacement deployment.

## 13. Rollback and retirement

`NebulaVerifiableAI` is non-upgradeable and cannot be deleted or rolled back.
Operational rollback means:

1. owner pauses the affected contract through a separately authorized action;
2. backend runners stop sending privileged transactions;
3. frontend/backend configuration stops advertising the address;
4. outstanding escrow and pending withdrawals are reconciled safely;
5. evidence and the invalid/retired address remain documented;
6. a replacement deployment follows this entire runbook with new approval;
7. consumers migrate only after the replacement manifest validates.

Never claim a replacement transaction erased or rewound prior chain history.

## 14. Secret cleanup and handoff

After the operation:

```bash
unset NEBULA_DEPLOYER_PRIVATE_KEY ETHERSCAN_API_KEY ARBITRUM_SEPOLIA_RPC
git status --short
git check-ignore -v contracts/.env.deploy.sepolia contracts/broadcast/
```

Do not delete evidence until receipts and sanitized public records are safely
captured. Never commit secret env files or Foundry broadcast journals. The
handoff must state whether broadcast occurred, list only public transaction
facts, record unresolved failures, and distinguish deployment, L2 receipt,
source verification, and application finality.
