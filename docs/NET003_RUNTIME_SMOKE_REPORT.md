# NET-003 Connected Sepolia Runtime Smoke Report

## Result

NET-003 passed on Arbitrum Sepolia (`421614`) against
`0xbD0A2f65ae2C67A313d2883cAed5029A3275a599`.

The executed topology was:

```text
HTTP API -> isolated nebula_sepolia PostgreSQL -> receipt runner
-> assignment runner -> deployed contract -> deterministic fixture worker
-> real ProofVerifier -> settlement runner -> event runner
-> reconciliation runner -> final HTTP API projection
```

The API, worker, and five runners ran as independent processes. The journeys
used public API interfaces and real signed testnet transactions. Direct database
access was limited to provisioning the isolated static model fixture and
read-only final assertions. No receipt, log, chain adapter, lifecycle transition,
or privileged contract call was fabricated.

## Successful journeys

Both jobs ended `completed`, with completed leases, valid proofs, matching API
reconciliation, settled contract state, finalized transaction projections, and
the five required finalized events.

### Journey 1

- UUID: `b508d8b9-2881-5645-a0b6-62eeb4abaa60`
- `createJob`: `0xb46b888aef5fbf38358af6fe1f1ea7f429f8019ed5f3caddf85d546e3937f1d9`, block `312825601`
- `assignProvider`: `0x3069f0ab1b1d6138b9e48c2486dd6bfebb0d72c2f597b0ea7c6e8a70d231c967`, block `312825668`, verifier nonce `22`
- `submitProof`: `0xa83217a4799f6965c6164b6ed2767f3d8e832e923feef47db96bf8b64ffdff40`, block `312825699`, verifier nonce `23`
- `verifyJob`: `0x947a467bdbb8dbc93feb5220b4cc2bc7cdc5059b0dbb3e86f137d68904f5ae15`, block `312825721`, verifier nonce `24`

### Journey 2

- UUID: `4f56df4a-94ad-5ad3-be26-1563e041acd2`
- `createJob`: `0xfbacea7c209b1e9e260b4b710de97fb6209816d0f8ae4c184140fdda889cff12`, block `312825752`
- `assignProvider`: `0x1ed1a6430d883189de0977c509d883b6045b948491fc1d137aa02f0d153976f1`, block `312825825`, verifier nonce `25`
- `submitProof`: `0x8707e1f46bad500e481a963f6e476ba7599d63c43d2654a943581a99ddfc7a49`, block `312825847`, verifier nonce `26`
- `verifyJob`: `0xc5fc73b18064afd6dd6d1a79c6947b565dbce20f5551ffd554f121b30a254759`, block `312825865`, verifier nonce `27`

For each journey, PostgreSQL contained finalized `JobCreated`,
`ProviderAssigned`, `ProofSubmitted`, `PaymentCredited`, and `JobSettled`
events whose transaction hashes and blocks matched the transaction projections.
The event cursor reached block `312825891` with `halted = false`, beyond both
settlements. Nonces `22` through `27` were unique and contiguous across the two
journeys.

The two successful jobs credited `100000` USDC base units in total. Because
earlier diagnostic journeys had also completed before final closure, the final
provider withdrawal collected `300000` accumulated base units:

- `withdraw`: `0x67f59e17c43bec8d7227072c141b8c309c7cd5dadd8807522ca27902d198bacd`
- Block: `312825890`
- Provider pending withdrawal after receipt: `0`

## Defects found and corrected

1. An authenticated heartbeat did not activate a newly registered pending GPU
   node, so the scheduler had no eligible node.
2. A missing prepared legacy transaction could remain below the RPC gas floor,
   block the verifier nonce, and prevent later assignments. The outbox now
   persists a same-nonce fee-bumped replacement before broadcasting it.
3. Assignment receipt timeouts were treated as proof of a dropped transaction.
   They now remain recoverable, and prepared dropped intents with unconsumed
   nonces can resume safely.
4. `/leases/next` could redeliver a lease after proof verification was queued;
   the subsequent worker failure path could invalidate successful work.
5. Overlap event polling could replay `ProviderAssigned` and regress a job from
   `verifying` to `assigned`. Assignment/proof projections are now monotonic.

The event runner used Arbitrum's official Sepolia RPC for read-only backfill
because the configured Alchemy plan rejected log ranges above ten blocks. The
official endpoint was preflighted for the same chain ID; signed transactions
continued to use the configured RPC.

## Verification

- Live NET-003 harness: `status: passed`
- Live evidence: 2 jobs, 2 leases, 2 valid proofs, 10 required job events
- Focused worker/outbox/dispatcher/event/route tests: `52 passed`
- Earlier combined focused regression: `44 passed`
- Final full backend regression: `269 passed, 69 skipped in 38.65s`
- Ruff and Python compilation: passed
- `git diff --check`: passed
- Repository-wide mypy remains a pre-existing gate failure: `350 errors in 29
  files`; NET-003 does not claim that baseline as resolved.

## Skill usage

### Discovered repository inventory

`solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`,
`diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`,
`improve-codebase-architecture`, `handoff`, `ask-matt`,
`setup-matt-pocock-skills`, `teach`, and `wizard`.

### Applied

1. `diagnosing-bugs`: traced failures through public API responses, runner logs,
   PostgreSQL projections, RPC receipts, contract state, nonce state, and cursor
   state before changing behavior.
2. `tdd`: observed red regressions before implementing node activation, fee
   replacement, dropped-intent recovery, and proof-queued lease suppression.
3. `domain-modeling`: kept AI user, GPU provider, GPU node, worker signer,
   backend verifier, lease, proof, and settlement identities separate.
4. `wizard`: provisioned ignored least-privilege runtime key files; the one-time
   wizard was removed after successful use.
5. `code-review`: ran separate standards and NET-003 specification reviews and
   strengthened per-journey evidence and typing based on their findings.

### Not applied

- `solidity-foundry-security`: no contract source or Foundry behavior changed.
- `research`: primary evidence came from the deployed chain and repository.
- `codebase-design`, `improve-codebase-architecture`: no broad refactor was
  authorized; fixes stayed at existing runtime seams.
- `grill-with-docs`, `ask-matt`, `setup-matt-pocock-skills`, `teach`: no new
  planning, routing, installation, or teaching task was required.
- `handoff`: this report itself provides the ticket handoff.

## Security note

No private key, database URL, JWT secret, or wallet credential is tracked by
this ticket. During diagnosis, the configured RPC URL appeared in a local
third-party traceback. Rotate that RPC credential after closure.
