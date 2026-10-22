# Nebula AI Cloud

**Trustless AI execution on distributed GPUs. Verify. Pay. Repeat.**

A publicly accessible, blockchain-backed GPU compute marketplace with cryptographic Proof-of-AI-Execution (PoAE).

## Architecture

```
Frontend (React + Vercel Hobby)
        │
        ▼
Backend API + runners (FastAPI + OCI Always Free)
        │
   ┌────┼────┬────────┐
   ▼    ▼    ▼        ▼
 Supabase  R2  Redis  IPFS
        │
        ▼
Blockchain (Arbitrum Sepolia)
        │
        ▼
Worker Nodes (Python + PyTorch)
```

## Project Structure

```
nebula-ai/
├── contracts/        # Solidity smart contract (Foundry)
├── backend/          # FastAPI backend
├── frontend/         # React frontend
├── worker/           # Python GPU worker
├── scripts/          # Deployment scripts
└── docs/             # Documentation
```

## Quick Start

### Ubuntu/WSL E2E setup

Use the repeatable setup wizard to install and verify the complete local
PostgreSQL + Anvil E2E toolchain. Inspect before allowing any changes:

```bash
./scripts/setup_e2e_wizard.sh --check
./scripts/setup_e2e_wizard.sh --plan
./scripts/setup_e2e_wizard.sh --install
```

After installation, reopen WSL if requested, rerun `--check`, and start the
guarded verification workflow:

```bash
./scripts/setup_e2e_wizard.sh --verify
```

`--verify` runs the canonical local PostgreSQL + Anvil backend/contract E2E
twice. It can additionally run the deployed browser-auth smoke when you provide
an existing HTTPS frontend origin; it does not deploy or start the unfinished
frontend application.

### Prerequisites
- Node.js 24 LTS
- Python 3.10+
- Foundry (for smart contracts)
- MetaMask wallet

### 1. Smart Contract
```bash
cd contracts
forge install OpenZeppelin/openzeppelin-contracts
forge test
```

### 2. Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```

### 4. Worker
```bash
cd worker
pip install -r requirements.txt
python setup.py  # Interactive setup
python worker.py
```

## Environment Variables

Copy `.env.example` to `.env` in each component directory and fill in your values.

## Documentation

- [Product Requirements Document](docs/NEBULA_PRD_v3.0.md)
- [Development Plan](docs/DEVELOPMENT_PLAN.md)
- [Zero-cost hosting decision](docs/research/BE002_ZERO_COST_HOSTING_OPTIONS.md)
- [BE-002 production browser-auth wizard](scripts/be002_production_auth_wizard.sh)
- [Temporary owner-operated demo-host runbook](docs/runbooks/OWNER_OPERATED_DEMO_HOST.md)
- [Temporary owner-operated demo-host wizard](scripts/be002_owner_operated_demo_wizard.sh)

## License

MIT
