# GCP-006 Controlled Laptop Demo Runtime

Status: owner-executed only during supervised testing or faculty demonstrations.

```bash
scripts/gcp006_laptop_demo_runtime_wizard.sh --check
scripts/gcp006_laptop_demo_runtime_wizard.sh --plan
scripts/gcp006_laptop_demo_runtime_wizard.sh --run
scripts/gcp006_laptop_demo_runtime_wizard.sh --status
scripts/gcp006_laptop_demo_runtime_wizard.sh --stop
```

`--run` validates local prerequisites and performs read-only Cloud Run,
Supabase, private R2, Arbitrum Sepolia RPC, and deployed-contract checks. It
then requires distinct GPU provider, Worker signer, and Verifier identities,
plus the existing separately controlled laptop executor identity.

The wizard creates protected environment files and six executable wrappers
outside Git: the Worker and receipt, assignment, settlement, event, and
reconciliation runners. It does not start anything while preparing them and
asks for an exact confirmation immediately before each process start.

The Worker uses the deterministic fixture adapter unless a separately reviewed
ticket authorizes something else. This is not real GPU proof. The five runners
and Worker run only on the owner laptop; Cloud Run remains one API container,
`RUNNERS_ENABLED=false`, request based, and minimum instances zero.

Use `--status` during the demonstration. Use `--stop` immediately afterward or
on any failure. The stop command sends `TERM` only to recorded PIDs and removes
their PID files. Review protected logs under the runtime state directory, but
do not copy tokens, private keys, database URLs, RPC credentials, cookies, or
presigned URLs into evidence.
