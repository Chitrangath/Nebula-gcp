## Faculty presentation guide

### 30 seconds

“Nebula is a testnet GPU marketplace. A user submits an approved AI inference
job, an independent GPU Worker executes it, the Worker signs tamper-evident
execution evidence, and Arbitrum Sepolia escrow credits the provider only after
the backend verifier accepts that evidence.”

### 2 minutes

Show the public frontend, connect the AI-user wallet, select ResNet50 or BERT,
submit one of the inputs in `demo-data/`, sign the escrow transaction, and
follow the job. Then show the provider network, Worker lease, result, PoAE
verdict, Arbitrum explorer transaction, and provider earnings. A second
provider can run another job or receive a reassignment after a lease expires.

### 5 minutes

Explain the separation of concerns: React/Vercel is the user interface;
Cloud Run/FastAPI authenticates, validates, schedules, and persists state;
private R2 stores bytes; PostgreSQL stores operational projections; the
provider Worker executes PyTorch and signs the proof envelope; and the
non-upgradeable Solidity contract holds USDC escrow and enforces terminal
settlement. The backend remains necessary because blockchain is not a file
store, scheduler, model registry, or query API.

Likely questions:

- **Is it fully trustless?** No. PoAE is tamper-evident signed evidence; the
  backend verifier remains trusted in this MVP.
- **Why use blockchain?** It provides independently inspectable escrow,
  settlement transitions, provider credit, refunds, and withdrawal history.
- **Why not run everything on-chain?** Model execution, files, scheduling, and
  proof traces are too large and operationally dynamic for the contract.
- **Can providers see input?** Yes. This MVP does not provide confidential
  inference; users should submit suitable demonstration data only.
- **Is this mainnet-ready?** No. It uses Arbitrum Sepolia test assets and a
  supervised owner-operated runner profile.