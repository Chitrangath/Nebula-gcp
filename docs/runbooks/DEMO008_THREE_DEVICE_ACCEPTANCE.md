# DEMO-008 Three-Device Acceptance

Status: implementation complete; owner-led three-device execution required.

## Purpose

This runbook proves the browser-led production journey with three physical demo
devices. It does not simulate a second provider and does not treat a local
fixture run as final acceptance.

| Device | Operator role | Processes |
|---|---|---|
| Device A | AI user | Production browser and wallet only |
| Device B | GPU provider and Verifier host | One real-model GPU Worker; the owner may also run the five controlled backend runners here |
| Device C | Independent GPU provider | One real-model GPU Worker only |

A Demo device is a physical computer. A GPU node is the registered scheduling
identity hosted by that computer, and a Worker is the software process serving
that node. Do not interchange these terms while presenting the network view.

## Before the session

1. Deploy the reviewed backend and frontend commits. Configure
   `DEMO_VERIFIER_NODE_ID` with Device B's registered node UUID.
2. On both GPU laptops, clone the same reviewed commit and run the repository
   E2E prerequisite wizard. Verify `nvidia-smi` and PyTorch CUDA.
3. Register Device B and Device C using distinct provider wallets, node UUIDs,
   node API keys, and Worker signers. Never transfer one device's API key or
   signer to the other.
4. Ensure Device A has Arbitrum Sepolia ETH and test USDC. Provider/executor
   wallets need only the testnet balance required by the existing runbook.
5. Keep every laptop awake and on mains power. Disable VPN/proxy software that
   blocks Cloud Run, R2, Supabase, or Arbitrum Sepolia.

## Commands

On **each GPU laptop**:

```bash
cd ~/Nebula-gcp
./scripts/demo008_provider_worker_wizard.sh --check
./scripts/demo008_provider_worker_wizard.sh --plan
./scripts/demo008_provider_worker_wizard.sh --run
./scripts/demo008_provider_worker_wizard.sh --status
```

The provider wizard verifies the reviewed Git commit, downloads and verifies
the pinned BERT vocabulary, and starts one `multimodel` CUDA Worker. The actual
BERT weights arrive through the private lease capability and are independently
checked by the Worker's hash-keyed model loader before execution. The wizard
asks only for that node's public configuration, API key, Worker signer, and
approved ResNet50 artifact URL. It never receives database, R2, AI-user,
Verifier, or backend-runner credentials.

On the **owner laptop**, start the five controlled backend runners with the
existing GCP-006 wizard. Decline its legacy fixture Worker prompt because the
real provider Worker is managed separately:

```bash
./scripts/gcp006_laptop_demo_runtime_wizard.sh --run
./scripts/gcp006_laptop_demo_runtime_wizard.sh --status
```

Then run the acceptance wizard and follow it in order:

```bash
./scripts/demo008_three_device_acceptance_wizard.sh --check
./scripts/demo008_three_device_acceptance_wizard.sh --plan
./scripts/demo008_three_device_acceptance_wizard.sh --run
```

## Browser-led acceptance journey

1. Device A connects its AI-user wallet to the production Vercel origin.
2. Open `/network`; verify Device B and Device C are online and show the
   expected model capabilities.
3. Submit a ResNet50 image, approve escrow, and keep its job page open until it
   shows a verified result, valid proof, settled chain state, provider credit,
   and confirmed explorer links.
4. Record the public job UUID and assigned node UUID in the acceptance wizard.
5. Stop the provider that did not run ResNet50. Once `/network` shows only the
   ResNet provider online, submit BERT and wait for its first assignment.
6. Stop that assigned Worker before completion and immediately restart the
   other provider. The BERT page must visibly enter retry/reassignment and then
   complete on the other node with at least two attempts and the same proof,
   settlement, result, and provider-credit evidence.
7. Copy a fresh Device A access token from the successful wallet-auth response
   into the wizard's hidden prompt. The token exists only for the probe process
   and is never written into evidence.
8. The probe reads both authoritative job responses and fails unless the jobs
   use the two required models, settle on distinct nodes, have matching proof
   fingerprints, and include confirmed escrow, assignment, proof, and
   settlement transactions.

## Evidence checklist

Save screenshots outside Git. Capture only:

- ResNet50 result and full lifecycle;
- BERT result and full lifecycle;
- `/network` with both providers online;
- `/network` with the interrupted provider offline;
- both provider dashboards showing their respective completed work;
- every displayed Arbitrum Sepolia transaction opened in Arbiscan.

Do not capture tokens, cookies, API keys, private keys, database/RPC URLs,
presigned object URLs, or secret-entry terminals. The machine-readable evidence
is written with mode `0600` under:

```text
~/.local/state/nebula-gcp/evidence/demo008-three-device.json
```

## Recovery and shutdown

- Worker fails before heartbeat: inspect its protected log, verify CUDA and the
  pinned vocabulary, rotate only that node's API key if authentication failed,
  then rerun the provider wizard.
- Job remains queued: confirm at least one compatible node is online and the
  assignment runner is running. Do not create another escrow until the first
  job reaches an explicit terminal/refund state.
- Job reaches proof submission but not settlement: preserve the public job ID,
  keep the five runners running, and inspect sanitized runner error types. Do
  not manually replay a signing transaction.
- Chain/database mismatch: stop submissions immediately and treat the
  reconciliation incident as authoritative.

Always stop the supervised processes after the session:

```bash
# On each GPU laptop
./scripts/demo008_provider_worker_wizard.sh --stop

# On the owner laptop
./scripts/gcp006_laptop_demo_runtime_wizard.sh --stop
```

Cloud Run remains API-only with `RUNNERS_ENABLED=false`, minimum instances
zero, and no GPU Worker.
