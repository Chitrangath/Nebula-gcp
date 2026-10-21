# Nebula AI Cloud

Nebula connects AI inference users with independently operated GPU providers and settles testnet escrow according to centrally verified execution evidence.

## Language

**AI user**:
A wallet-identified participant that submits and funds inference jobs.
_Avoid_: Customer, developer

**Job**:
One request to run one versioned approved model against one exact input for one fixed testnet price.
_Avoid_: Task, workload

**GPU provider**:
A wallet-identified participant that operates one or more GPU nodes and may earn testnet payment for valid jobs.
_Avoid_: Miner, host

**GPU node**:
A provider-operated machine registered to receive compatible job leases.
_Avoid_: Provider, worker

**Worker**:
The Nebula software process running on a GPU node that executes the model adapter and produces PoAE evidence.
_Avoid_: Node, provider

**Model artifact**:
The immutable, hash-identified weight data for one version of an approved model.
_Avoid_: Model code, checkpoint

**Model adapter**:
The versioned worker rules that build an approved model, preprocess its input, execute inference, and serialize its output and checkpoints.
_Avoid_: Model artifact, dynamic plugin

**Worker signer**:
A node-specific signing identity authorized by the GPU provider and used to sign proof envelopes.
_Avoid_: Provider wallet, verifier

**Lease**:
A time-bounded exclusive assignment of a job to one GPU node.
_Avoid_: Job, reservation

**Job fingerprint**:
A deterministic hash binding a job to its protocol version, model identity, immutable model artifact, preprocessing version, and exact input.
_Avoid_: Job hash, proof hash

**Checkpoint**:
A named model-specific point whose intermediate inference value is committed to the execution trace.
_Avoid_: Snapshot, layer proof

**Execution trace**:
The ordered set of checkpoint names and hashes captured for one inference execution.
_Avoid_: Log, full trace

**Proof envelope**:
The versioned worker-signed package containing the job fingerprint, execution trace commitment, output hash, and job-binding metadata.
_Avoid_: Zero-knowledge proof, correctness proof

**PoAE proof**:
The user-facing name for a proof envelope produced by Nebula's Simplified Proof-of-AI-Execution protocol.
_Avoid_: Trustless proof, mathematical proof of execution

**Verifier**:
The trusted Nebula backend role that validates a proof envelope and authorizes its settlement verdict.
_Avoid_: Validator, oracle

**Verdict**:
The verifier's terminal `VALID` or `INVALID` decision for a job's proof envelope.
_Avoid_: Proof result, job status

**Settlement**:
The single terminal escrow outcome that credits either provider earnings or a user refund.
_Avoid_: Payment, verification
