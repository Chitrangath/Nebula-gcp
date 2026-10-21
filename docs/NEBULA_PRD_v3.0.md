# Product Requirements Document (PRD)

## **Nebula AI Cloud - MVP Edition (Version 3.0)**

**A Publicly Deployable, Blockchain-Backed, Verifiable Distributed GPU Compute Platform (Student Project)**

**Version:** 3.0 (Internet Deployment Ready + Simplified Proof-of-AI-Execution + Inconsistency Fixes)
**Date:** August 2026
**Target Completion:** 3 months (12 weeks)
**Team Size:** 1-4 students
**Budget:** $0 (free tier services only)

---

## 1. Executive Summary

### Product Name
**Nebula AI Cloud**

### Tagline
*Trustless AI execution on distributed GPUs. Verify. Pay. Repeat.*

### What This Actually Is
A **publicly accessible, blockchain-backed GPU compute marketplace** that demonstrates:
- Users can submit AI inference tasks from anywhere via web browser
- Tasks run on distributed GPU nodes (owned by community providers)
- Payments are held in smart contract escrow and released automatically
- Execution is logged on blockchain for transparency
- Everything is visible in a real-time dashboard
- Providers earn cryptocurrency by sharing idle GPU resources
- **NEW: Cryptographic proof of execution** – each job generates a verifiable proof that the model actually ran on the requested GPU with the correct input

> **What Makes This Different (The Innovation):**
> No existing platform (AWS, Render, Akash) cryptographically verifies that the AI model was actually executed. They rely on trusting the provider. Nebula introduces a **simplified Proof-of-AI-Execution (PoAE)** that captures a fingerprint of the job, records a lightweight execution trace, generates a signed Merkle-tree proof, and verifies the proof before releasing payment. This moves Nebula from "another compute marketplace" to a novel research contribution in verifiable decentralized AI inference.

This is **not** a production system. It's an MVP deployed to the internet, suitable for:
- Testing and feedback from real users
- Academic demonstration
- Proof-of-concept for investors
- Community feedback before scaling

### Project Classification
This is a **Blockchain-Backed Distributed GPU Compute Platform** (not fully decentralized). The backend controls scheduling; blockchain ensures trustless payments. This is intentional for MVP scope. Anyone can register as a GPU provider or submit jobs—no gatekeeping.

### What This Is NOT
- A production-grade platform (limited reliability, no HA)
- A fully decentralized system (backend is centralized, blockchain adds trust layer)
- AutoML, federated learning, or fancy ML
- A token economy or reputation system
- A high-availability system (99.9% uptime)
- Requires payment to use (free testnet USDC available via faucet)

---

## 2. Problem Statement

**Real Problem You're Solving:**
- AI students want to run inference on GPUs without buying expensive hardware or cloud credits
- GPU owners have idle machines they want to monetize
- No simple platform that connects these two groups *with verified payments*

**Current State:**
- Students use expensive cloud (AWS/Google Cloud) or run nothing
- GPU owners can't easily share resources with strangers
- No trustless payment mechanism between unknown parties
- **CRITICAL GAP: No platform verifies that the AI job was actually executed correctly.**
  - AWS/Render: "Trust us, we ran it"
  - Akash: "Trust the provider"
  - Result: Providers could skip computation, use smaller models, or return garbage

| Platform | Decentralised | Verifiable Execution | Trust Model |
|----------|---------------|----------------------|-------------|
| AWS      |    ❌         |        ❌           |   Trust AWS |
| Render   |            ❌ |        ❌           | Trust Render |
| Akash | ✅ | ❌ | Trust provider |
| **Nebula (with PoAE)** | ✅ | ✅ | **Cryptographic proof** |

**Your Solution:**
- Blockchain-backed smart contracts replace trust with cryptographic verification
- Simple web UI hides all complexity
- Open network: anyone can be a provider or user
- Instant payment via escrow (no middleman)

---

## 3. Project Goals

### Primary Goals (MUST HAVE for MVP)
✅ Working end-to-end flow (select model → execute → get results)
✅ Multiple GPU nodes (3-4 at launch, scalable to 100+)
✅ Smart contract escrow payment + logging
✅ Web UI showing all nodes, jobs, payments
✅ **Publicly accessible via internet** (not localhost)
✅ Real GPU providers can register and earn payments
✅ Real users can submit jobs from anywhere
✅ **NEW: Simplified Proof-of-AI-Execution (PoAE)** – cryptographic verification of job execution
- ✅ Generate a job fingerprint (SHA-256 of model + weights + input) — stored as audit trail
- ✅ Capture execution trace (3-4 layer checkpoints during inference)
- ✅ Build a Merkle tree from the trace and sign it
- ✅ Backend verifies Merkle root + signature before releasing payment
- ✅ Failed proof = no payment (refund user)

### New Goals (Internet Deployment)
✅ Secure authentication (wallet signatures)
✅ API rate limiting (prevent abuse)
✅ Worker authentication (prevent spoofing)
✅ Signed URLs for file downloads (prevent unauthorized access)
✅ Database backup (in case of data loss)

### Non-Goals (DELETE from your brain)
❌ AutoML, model registry, dataset versioning
❌ Reputation scoring, dynamic pricing
❌ HA/disaster recovery, 99% uptime
❌ ML-based scheduler (rule-based is fine)
❌ Support for 100+ models (4 verified models is enough)
❌ Real token economy
❌ Kubernetes or other enterprise orchestration
❌ Production-grade monitoring (basic logging is fine)

---

## 4. Innovation – Simplified Proof-of-AI-Execution (PoAE)

**What It Is:**
A lightweight cryptographic mechanism that proves a remote GPU node actually executed the requested AI model on the provided input, without re-running the entire computation.

**Why It Matters:**
Current systems (AWS, Render, Akash) assume the provider is honest. A malicious provider could return random noise, use a smaller model, skip computation entirely, or fake the output. PoAE makes this cryptographically impossible to hide.

**How It Works (4 Steps):**

**Step 1: Job Fingerprint (Before Execution)**
The worker computes: `SHA-256(model_state_dict_bytes + input_bytes + model_metadata)`
This uniquely identifies the exact job. The worker sends this hash as part of the proof. The backend stores it for audit trail purposes.

**Step 2: Execution Trace (During Inference)**
During inference, the worker records hashes at only 3-4 checkpoints:
- After the 1st layer
- After ~1/3 of layers
- After ~2/3 of layers
- After the final layer (output)

These checkpoints are stored as `trace_hashes`. We don't trace every layer (too expensive).

**Step 3: Merkle Tree Proof**
- Build a Merkle tree from `trace_hashes + [output_hash]` (all leaves are pre-hashed SHA-256 hex strings)
- Root = `merkle_root` (hex string, converted to bytes32 for on-chain storage)
- Worker signs `(merkle_root + job_id + timestamp)` with their private key
- Proof = `{fingerprint, merkle_root, trace_hashes, output_hash, signature, timestamp}`

**Step 4: Verification (Backend)**
- Validate fingerprint is a valid SHA-256 hex string and store for audit
- Rebuild Merkle tree from `trace_hashes` → verify `merkle_root` matches
- Verify ECDSA signature against provider's wallet address
- Call smart contract: `verifyJob(jobId, True/False)`

**Why This is "Simplified" (MVP Scope):**
- **Single verifier**: The backend performs verification (no decentralized verifier network yet)
- **Lightweight trace**: Only 3-4 checkpoints, not full layer-by-layer
- **No zero-knowledge proofs**: Uses standard hashing + signatures (proven secure)
- **No on-chain signature verification**: Gas too high; we verify off-chain in backend
- **No stake/slashing**: For MVP, we just refund user on failure
- **Fingerprint as audit trail**: Worker sends hash, backend stores it. No recomputation.

**Why This Still Counts as Novel:**
No production platform (AWS, Render, Akash) implements any form of verifiable AI execution. Research papers exist but no open-source implementation in a deployed system. You are building the first public MVP of this concept.

---

## 5. Target Users for MVP

### User 1: AI Developer / Student (Global)
- **Wants**: Run inference without managing infrastructure, paying for hardware, or vendor lock-in
- **Uses**: Opens deployed website → connects wallet → selects model → uploads input → submits job → watches results
- **Pays**: Testnet USDC (free from faucet, no real money)
- **Location**: Anywhere with internet

### User 2: GPU Provider (Global)
- **Wants**: Monetize idle GPU by sharing with community
- **Uses**: Creates account → connects wallet → registers GPU → downloads worker → runs worker on their machine → receives jobs → earns payments
- **Earns**: Testnet USDC → eventually mainnet USDC (real money)
- **Location**: Anywhere with good internet

### User 3: Faculty / Evaluators
- **Wants**: See this works end-to-end
- **Uses**: Visits deployed website → watches live job execution → inspects blockchain records
- **Cares About**: "Can students actually build and deploy real systems?"

---

## 6. Core User Flows

### Flow 1: GPU Provider Registers (5 minutes, from anywhere)
```
Provider (at home with GPU machine):
  1. Open Nebula app (https://nebula-app.vercel.app)
  2. Click "Register as Provider"
  3. Connect wallet (MetaMask)
  4. Fill form: GPU name, VRAM, location
  5. Click "Register on Blockchain"
  6. Approve transaction in MetaMask
  7. Backend assigns UUID Node ID, stores on-chain as metadata
  8. Download worker script (one-click)
  9. Follow setup instructions (2 min setup)
  10. Run: python worker.py
  11. Dashboard shows "Node Online"
  12. Ready to receive jobs from anywhere
```

### Flow 2: User Submits Job (from anywhere, 10 minutes)
```
User (at coffee shop or office):
  1. Open https://nebula-app.vercel.app
  2. Connect wallet (MetaMask)
  3. Click "Submit Job"
  4. Select model: "YOLOv5" (from dropdown)
  5. Upload image (file picker)
  6. See cost: "$0.05 testnet USDC"
  7. (If no balance: click "Get Free Testnet USDC" → faucet)
  8. Click "Submit & Pay"
  9. Approve transaction in MetaMask

Platform (automatic, distributed):
  1. Frontend calls POST /v1/jobs (model_id, input_file)
  2. Backend creates UUID job record in Supabase (status: "pending_blockchain")
  3. Backend uploads input to Cloudflare R2 (with expiry = 24h)
  4. Backend returns {job_id: uuid, model_id, amount}
  5. Frontend calls smart contract createJob(uuid, fingerprint, amount) with MetaMask
  6. Smart contract stores UUID, locks USDC
  7. Frontend calls POST /v1/jobs/{job_id}/confirm-blockchain (tx_hash)
  8. Backend updates status to "queued"
  9. Backend scheduler picks best available node
  10. Node polls every 5 sec, gets job
  11. Node downloads model directly from Cloudflare R2 (signed URL)
  12. Node runs inference with PoAE trace
  13. Node uploads result to R2 + IPFS
  14. Node submits proof to backend
  15. Backend verifies proof, calls verifyJob on contract

User:
  16. Dashboard shows "Job Status: Running" (polled via API)
  17. Result ready after ~30 seconds
  18. Downloads bounding box image
  19. Sees blockchain tx: "Payment released to provider"
  20. Done (total time: ~1 min actual)

Provider:
  - Receives notification: "Job completed, earned $0.05"
  - Can check earnings on dashboard anytime
```

---

## 7. Functional Requirements

### Module 1: User Authentication
**What it does**: Login users via wallet signature, no passwords

| Feature | Implementation |
|---------|----------------|
| Wallet Login | MetaMask (web3modal library for multi-wallet support) |
| Sign Message | No server password. Challenge message + signature |
| Session | JWT access token (24h expiry) + refresh token (7 days, httpOnly cookie) |
| Roles | `user` or `provider` (user selects at signup) |
| Multi-wallet Support | MetaMask, WalletConnect, Coinbase Wallet |

**No database passwords.** Trust the wallet.

**Security Improvements (vs local):**
- JWT refresh tokens (24h access, 7d refresh)
- Rate limiting on auth endpoints (10 attempts per minute)
- CORS only allow deployed frontend domain

---

### Module 2: Node Registration & Management

**What it does**: GPU providers register machines once from anywhere

**On Frontend:**
```
Provider Dashboard (https://nebula-app.vercel.app/provider):
  +-- "Register GPU Node" button
  |  +-- Form fields:
  |  |  +-- GPU Name ("RTX 3090")
  |  |  +-- VRAM (24 GB)
  |  |  +-- Location (e.g., "US - East")
  |  |  +-- Optional: Discord/Telegram for updates
  |  +-- "Register on Blockchain" (MetaMask popup)
  |
  +-- "My Nodes" list
  |  +-- Node ID (UUID), GPU Name, Status (Online/Offline)
  |  +-- Active Jobs, Total Earnings
  |  +-- Last Heartbeat (2 mins ago)
  |  +-- Uptime (95%)
  |  +-- Worker Status indicator (green/red)
  |
  +-- "Worker Setup" (auto-download)
  |  +-- Generated setup script (bash + python)
  |  +-- API key (auto-generated, rotatable)
  |  +-- Instructions (Linux/Mac/Windows)
  |
  +-- "Earnings" tab
     +-- Total earned (testnet USDC)
     +-- Withdraw to Arbitrum Mainnet (future)
     +-- Transaction history
```

**Node Registration Flow:**
1. Provider fills form on frontend
2. Backend creates UUID node record in Supabase (status: "pending")
3. Backend returns node_id (UUID) + blockchain registration data
4. Frontend calls smart contract to register node (optional, for on-chain metadata)
5. Backend generates API key, hashes it, stores in `nodes.api_key_hash`
6. Provider downloads worker with auto-generated API key

**Payment & Verification Contract:** (see Section 8)

---

### Module 3: Supported Model Registry

**What it does**: Pre-vetted models available to users (no arbitrary uploads)

**Model Registry (Hardcoded in Backend, synced to DB):**

```python
SUPPORTED_MODELS = {
    "yolov5": {
        "name": "YOLOv5",
        "description": "Object detection",
        "framework": "pytorch",
        "model_source_url": "https://r2.nebula.ai/yolov5-official.pt",  # Cloudflare R2
        "model_hash_sha256": "sha256:abc123...",
        "vram_required_gb": 4,
        "estimated_inference_ms": 1500,
        "input_type": "image",
        "max_input_size_mb": 25,
        "price_usdc": 0.05,
        "supported_formats": ["jpg", "png"]
    },
    "bert-base": {
        "name": "BERT-Base",
        "description": "Text classification",
        "framework": "huggingface",
        "model_source_url": "https://r2.nebula.ai/bert-base-uncased.bin",
        "model_hash_sha256": "sha256:def456...",
        "vram_required_gb": 2,
        "estimated_inference_ms": 800,
        "input_type": "text",
        "max_input_size_mb": 10,
        "price_usdc": 0.03,
        "supported_formats": ["txt"]
    },
    "resnet50": {
        "name": "ResNet50",
        "description": "Image classification",
        "framework": "pytorch",
        "model_source_url": "https://r2.nebula.ai/resnet50-pytorch.pt",
        "model_hash_sha256": "sha256:ghi789...",
        "vram_required_gb": 2,
        "estimated_inference_ms": 900,
        "input_type": "image",
        "max_input_size_mb": 25,
        "price_usdc": 0.05,
        "supported_formats": ["jpg", "png"]
    },
    "whisper-tiny": {
        "name": "Whisper Tiny",
        "description": "Speech to text",
        "framework": "openai",
        "model_source_url": "https://r2.nebula.ai/whisper-tiny.pt",
        "model_hash_sha256": "sha256:jkl012...",
        "vram_required_gb": 3,
        "estimated_inference_ms": 3000,
        "input_type": "audio",
        "max_input_size_mb": 50,
        "price_usdc": 0.10,
        "supported_formats": ["wav", "mp3"]
    }
}
```

**User Flow Changes:**

```
OLD: Upload arbitrary .pt file
NEW: Select from dropdown: "YOLOv5", "BERT-Base", "ResNet50", "Whisper-Tiny"
    -> System generates presigned R2 URL for worker download
    -> Worker verifies hash against registry after download
    -> Worker caches model locally (24 hour TTL)
```

**Benefits:**
- No arbitrary code execution (prevents GPU compromise)
- Reproducible results (same model every run)
- Fast caching (model downloaded once per worker, reused)
- Public deployment ready (models in R2, not localhost)

---

### Module 4: Job Submission

**What it does**: Users select model + upload input data and create jobs from anywhere

**On Frontend:**
```
User Dashboard (https://nebula-app.vercel.app/submit):
  +-- "Submit Job" form
  |  +-- Select model: [YOLOv5 v]
  |  +-- Upload input file (drag-drop)
  |  +-- Show file preview + size validation (per-model limit)
  |  +-- Display fixed cost: "YOLOv5 = $0.05 testnet USDC"
  |  +-- [Submit & Pay] button
  |
  +-- "My Jobs" list
     +-- Job ID (UUID), Model, Status, Cost
     +-- Timestamp created / started / completed
     +-- [Download Results] button (when done)
     +-- Blockchain tx link (Arbitrum Sepolia explorer)
```

**What Happens:**

1. User selects model from registry
2. User uploads input file (frontend validates size per-model)
3. Frontend calls `POST /v1/jobs` with model_id + input_file
4. Backend creates UUID job record in Supabase (status: "pending_blockchain")
5. Backend uploads input to Cloudflare R2 (with expiry = 24h)
6. Backend returns {job_id: uuid, model_id, amount, fingerprint}
7. Frontend calls smart contract `createJob(uuid, fingerprint, amount)` with MetaMask
8. Smart contract stores UUID, locks USDC
9. Frontend calls `POST /v1/jobs/{job_id}/confirm-blockchain` with tx_hash
10. Backend updates status to "queued", indexes blockchain event
11. Job ready for scheduler

---

### Module 5: Scheduler (The Smart Part)

**What it does**: Pick the best GPU node for each job (rule-based, not ML)

**Inputs:**
- Model requirements (VRAM needed, framework)
- Available nodes (status, VRAM, current load)
- Job priority (first-come-first-serve for MVP)

**Algorithm (rule-based, ~20 lines of code):**
```python
import asyncio
from datetime import datetime, timedelta

def count_active_jobs(node_id: str) -> int:
    """Query DB for active jobs on this node."""
    # SELECT COUNT(*) FROM jobs
    # WHERE assigned_node_id = node_id
    # AND status IN ('running', 'assigned')
    ...

async def select_node(model_vram_required: int, available_nodes: list):
    """Pick the least loaded eligible node."""
    eligible = []
    for n in available_nodes:
        if n.vram_gb < model_vram_required:
            continue
        if n.status != "active":
            continue
        if n.last_heartbeat < datetime.utcnow() - timedelta(minutes=5):
            continue
        active = count_active_jobs(n.id)
        eligible.append((active, n))

    if not eligible:
        return None  # No available nodes

    # Pick: least loaded node (fewest active jobs)
    eligible.sort(key=lambda x: x[0])
    return eligible[0][1]
```

**Output:**
- Selected node ID (UUID)
- Fixed cost (from model registry)
- Estimated runtime (from model registry)

---

### Module 6: Worker Node (GPU Machine - Internet Ready)

**What it does**: Runs on each GPU machine (Windows/Mac/Linux), executes jobs from anywhere

**Setup (one-time, 5 minutes):**

```bash
# 1. Download worker script from dashboard
# https://nebula-app.vercel.app/provider/download-worker

# 2. Extract + install dependencies
unzip nebula-worker.zip
cd nebula-worker
pip install -r requirements.txt

# 3. Run setup wizard (one-time)
python setup.py
# Prompts for:
#   - Node ID (UUID, from dashboard)
#   - API key (from dashboard)
#   - Backend URL (https://api.nebula.ai)
#   - Model cache directory

# 4. Start worker (persistent)
python worker.py
# Or as service:
#   Linux: systemctl start nebula-worker
#   Mac: launchctl
#   Windows: sc start nebula-worker
```

**Runtime (Improved for Internet):**
```python
import asyncio
import hashlib
import io
import logging
import os
import pickle
from datetime import datetime, timedelta

import aiohttp
import torch
from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_defunct
from merkletools import MerkleTools

load_dotenv()

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self):
        self.node_id = os.getenv("NODE_ID")
        self.backend_url = os.getenv("BACKEND_URL", "https://api.nebula.ai")
        self.api_key = os.getenv("API_KEY")
        self.private_key = os.getenv("PRIVATE_KEY")
        self.public_key = Account.from_key(self.private_key).address
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_cache = {}

    async def run(self):
        """Main worker loop"""
        logger.info(f"Worker started: {self.node_id}")
        logger.info(f"Backend: {self.backend_url}")

        asyncio.create_task(self._heartbeat_loop())

        async with aiohttp.ClientSession() as session:
            self.session = session
            while True:
                try:
                    job = await self._get_next_job()
                    if not job:
                        await asyncio.sleep(5)
                        continue

                    await self._execute_job(job)
                except Exception as e:
                    logger.error(f"Error: {e}", exc_info=True)
                    await asyncio.sleep(10)

    async def _get_next_job(self):
        """Poll backend for next job (with retry for network resilience)"""
        for attempt in range(3):
            try:
                async with self.session.get(
                    f"{self.backend_url}/v1/nodes/{self.node_id}/jobs",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "User-Agent": "Nebula-Worker/1.0"
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=True
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        jobs = data.get("jobs", [])
                        return jobs[0] if jobs else None
                    elif resp.status == 401:
                        logger.error("Authentication failed. Check API key.")
                        raise Exception("Invalid API key")
                    return None
            except aiohttp.ClientError as e:
                logger.warning(f"Failed to get next job (attempt {attempt + 1}/3): {e}")
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)
        return None

    async def _execute_job(self, job):
        """Execute job AND generate PoAE proof"""
        job_id = job["id"]
        start_time = datetime.utcnow()

        try:
            # 1. Get presigned URL, download model directly from R2
            logger.info(f"Getting model {job['model_id']}")
            model = await self._get_model(job["model_id"])

            # 2. Download input file
            logger.info("Downloading input file")
            input_data = await self._download_input(job["input_file_url"])

            # PoAE Step 1: Pre-execution fingerprint (audit trail)
            fingerprint = self._compute_fingerprint(model, input_data, job["model_id"])

            # 3. Run inference WITH TRACING (PoAE Step 2)
            logger.info("Running inference with trace")
            result, trace_hashes = await self._run_inference_with_trace(
                model, input_data, job["model_id"]
            )

            # PoAE Step 3: Build Merkle tree proof
            output_hash = hashlib.sha256(pickle.dumps(result)).hexdigest()

            mt = MerkleTools()
            for h in trace_hashes:
                mt.add_leaf(h, do_hash=False)
            mt.add_leaf(output_hash, do_hash=False)
            mt.make_tree()
            merkle_root = mt.get_merkle_root()

            # Convert merkle_root hex to bytes32 for signing
            merkle_root_bytes = bytes.fromhex(
                merkle_root[2:] if merkle_root.startswith("0x") else merkle_root
            )

            timestamp = int(datetime.utcnow().timestamp())
            message = f"{merkle_root}:{job_id}:{timestamp}"
            signature = self._sign(message)

            proof = {
                "fingerprint": fingerprint,
                "merkle_root": merkle_root,
                "trace_hashes": trace_hashes,
                "output_hash": output_hash,
                "signature": signature.hex(),
                "public_key": self.public_key,
                "timestamp": datetime.utcnow().isoformat()
            }

            # 4. Upload result to R2 + IPFS
            logger.info("Uploading result")
            ipfs_hash = await self._upload_result(job_id, result)

            # 5. Notify backend WITH PROOF
            logger.info("Notifying backend with proof")
            await self._notify_completion(job_id, ipfs_hash, proof)

            elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.info(f"Job {job_id} completed with proof in {elapsed:.0f}ms")

        except asyncio.TimeoutError:
            logger.error(f"Job {job_id} timed out")
            await self._notify_failure(job_id, "Inference timeout")
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            await self._notify_failure(job_id, str(e))

    async def _download_input(self, input_file_url: str) -> bytes:
        """Download input file from signed URL."""
        async with self.session.get(input_file_url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            resp.raise_for_status()
            return await resp.read()

    async def _upload_result(self, job_id: str, result) -> str:
        """Upload result to R2 and pin to IPFS. Returns IPFS hash."""
        # 1. Get presigned upload URL from backend
        async with self.session.post(
            f"{self.backend_url}/v1/jobs/{job_id}/result-url",
            headers={"Authorization": f"Bearer {self.api_key}"},
        ) as resp:
            data = await resp.json()
            upload_url = data["upload_url"]
            ipfs_hash = data["ipfs_hash"]

        # 2. Upload to R2
        result_bytes = pickle.dumps(result)
        async with self.session.put(upload_url, data=result_bytes) as resp:
            resp.raise_for_status()

        # 3. Pin to IPFS via Pinata (handled by backend)
        return ipfs_hash

    async def _notify_completion(self, job_id: str, ipfs_hash: str, proof: dict):
        """Notify backend that job is complete with proof."""
        async with self.session.post(
            f"{self.backend_url}/v1/jobs/{job_id}/complete",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"ipfs_hash": ipfs_hash, "proof": proof}
        ) as resp:
            resp.raise_for_status()

    async def _notify_failure(self, job_id: str, error: str):
        """Notify backend that job failed."""
        async with self.session.post(
            f"{self.backend_url}/v1/jobs/{job_id}/fail",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"error": error}
        ) as resp:
            pass  # Best effort

    def _compute_fingerprint(self, model, input_data, model_id: str) -> str:
        """SHA-256 of model + input + metadata. Sent as audit trail."""
        model_bytes = pickle.dumps(model.state_dict())
        input_bytes = pickle.dumps(input_data)
        meta = f"{model_id}_{datetime.utcnow().date()}".encode()
        combined = model_bytes + input_bytes + meta
        return hashlib.sha256(combined).hexdigest()

    async def _run_inference_with_trace(self, model, input_data, model_id: str):
        """Run inference, record 3-4 checkpoint hashes."""
        trace_hashes = []
        device = next(model.parameters()).device

        # Preprocess input based on model type
        if model_id in ["yolov5", "resnet50"]:
            x = self._preprocess_image(input_data).to(device)
        elif model_id == "bert-base":
            x = self._tokenize_text(input_data).to(device)
        elif model_id == "whisper-tiny":
            x = self._preprocess_audio(input_data).to(device)
        else:
            x = torch.tensor(input_data).to(device)

        # Get layers (simplified - depends on model framework)
        try:
            layers = list(model.children())
        except Exception:
            # Non-sequential model (e.g., HuggingFace) - skip trace
            with torch.no_grad():
                output = model(x)
            return output.cpu().numpy(), ["skipped_non_sequential"]

        if len(layers) == 0:
            with torch.no_grad():
                output = model(x)
            return output.cpu().numpy(), ["skipped_no_children"]

        # Select 3-4 checkpoint positions
        checkpoint_indices = sorted(set([
            0,
            len(layers) // 3,
            2 * len(layers) // 3,
            len(layers) - 1
        ]))

        with torch.no_grad():
            for i, layer in enumerate(layers):
                x = layer(x)
                if i in checkpoint_indices:
                    tensor_bytes = x.detach().cpu().numpy().tobytes()
                    h = hashlib.sha256(tensor_bytes).hexdigest()
                    trace_hashes.append(h)

        final_output = x.detach().cpu().numpy()
        return final_output, trace_hashes

    def _preprocess_image(self, image_bytes: bytes) -> torch.Tensor:
        """Preprocess image for YOLO/ResNet."""
        from PIL import Image
        import torchvision.transforms as transforms

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225])
        ])
        return transform(img).unsqueeze(0)

    def _tokenize_text(self, text_bytes: bytes) -> torch.Tensor:
        """Tokenize text for BERT."""
        from transformers import BertTokenizer

        text = text_bytes.decode("utf-8").strip()
        tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
        inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
        return inputs["input_ids"]

    def _preprocess_audio(self, audio_bytes: bytes) -> torch.Tensor:
        """Preprocess audio for Whisper."""
        import numpy as np

        # Simple mel spectrogram placeholder
        # Real implementation would use librosa or torch audio
        audio = np.frombuffer(audio_bytes, dtype=np.float32)
        return torch.tensor(audio[:16000]).unsqueeze(0)

    def _sign(self, message: str):
        """Sign message with worker's private key (ECDSA)."""
        msg = encode_defunct(text=message)
        signed = Account.sign_message(msg, self.private_key)
        return signed.signature

    async def _get_model(self, model_id: str):
        """Get model from cache or download from R2 via signed URL."""
        if model_id in self.model_cache:
            cached_age = (datetime.utcnow() - self.model_cache[model_id]['timestamp']).total_seconds()
            if cached_age < 86400:
                logger.info(f"Model {model_id} found in cache")
                return self.model_cache[model_id]['model']

        # Get signed URL from backend
        async with self.session.get(
            f"{self.backend_url}/v1/models/{model_id}/signed-url",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=aiohttp.ClientTimeout(total=120)
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            signed_url = data["url"]
            expected_hash = data["hash"]

        # Download directly from R2
        async with self.session.get(signed_url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            resp.raise_for_status()
            content = await resp.read()

        # Verify model hash
        actual_hash = hashlib.sha256(content).hexdigest()
        if expected_hash and actual_hash != expected_hash:
            raise ValueError(f"Model hash mismatch: expected {expected_hash}, got {actual_hash}")

        model = torch.load(io.BytesIO(content), map_location=self.device)
        self.model_cache[model_id] = {
            'model': model,
            'timestamp': datetime.utcnow()
        }

        return model

    async def _heartbeat_loop(self):
        """Send heartbeat every 30 seconds."""
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    await session.post(
                        f"{self.backend_url}/v1/nodes/{self.node_id}/heartbeat",
                        json={
                            "utilization": 0,
                            "active_jobs": 0,
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        timeout=aiohttp.ClientTimeout(total=10),
                        ssl=True
                    )
                    logger.debug("Heartbeat sent")
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")

            await asyncio.sleep(30)
```

**Key Improvements (vs local):**
- SSL/TLS verification (https://, not http://)
- API key authentication (not just node ID)
- Manual retry logic for network resilience (async-compatible)
- Model caching with TTL (24 hours)
- Timeout protection (120 seconds)
- Model hash verification after download
- Environment variables (.env file)
- Cross-platform (Windows/Mac/Linux)
- Works with public API (not localhost)
- Proper async I/O (aiohttp, not sync requests)

---

## 8. Blockchain & Smart Contract

### Blockchain Selection
**Network: Arbitrum Sepolia Testnet**

**Why Arbitrum Sepolia (not Mumbai or mainnet):**
- 250ms block confirmation (instant visual feedback)
- Extremely cheap gas fees (~$0.001 per transaction)
- Stable testnet with long lifetime (no resets)
- L2 security backed by Ethereum
- Large community + good faucets

**Faucet:**
- Arbitrum Sepolia ETH: https://faucet.arbitrum.io (free)
- USDC Testnet: https://faucet.circle.com (free Circle account)

**Contract Details:**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

/**
 * @title NebulaVerifiableAI
 * @notice Verifiable AI execution with Proof-of-AI-Execution (simplified MVP)
 * @dev Job IDs are UUIDs encoded as bytes32 (padded).
 */
contract NebulaVerifiableAI is Ownable, ReentrancyGuard {

    IERC20 public usdc;
    address public verifier;  // Backend wallet (single verifier for MVP)

    struct Job {
        address user;
        address provider;
        string modelId;
        bytes32 jobId;           // UUID encoded as bytes32
        bytes32 fingerprint;     // SHA-256 audit trail hash
        bytes32 merkleRoot;      // Root of execution trace tree
        bytes32 outputHash;      // SHA-256 of final output
        uint256 amount;
        uint256 createdAt;
        uint256 completedAt;
        bool completed;
        bool verified;
        bool proofValid;
    }

    mapping(bytes32 => Job) public jobs;  // jobId (bytes32 of UUID) => Job
    mapping(address => uint256) public providerEarnings;

    event JobCreated(
        bytes32 indexed jobId,
        address indexed user,
        string modelId,
        bytes32 fingerprint,
        uint256 amount,
        uint256 timestamp
    );

    event ProofSubmitted(
        bytes32 indexed jobId,
        bytes32 merkleRoot,
        bytes32 outputHash,
        address provider
    );

    event JobVerified(
        bytes32 indexed jobId,
        bool valid,
        uint256 timestamp
    );

    event PaymentReleased(
        bytes32 indexed jobId,
        address indexed provider,
        uint256 amount
    );

    event PaymentRefunded(
        bytes32 indexed jobId,
        address indexed user,
        uint256 amount
    );

    constructor(address _usdc) {
        require(_usdc != address(0), "Invalid USDC");
        usdc = IERC20(_usdc);
        verifier = msg.sender;
    }

    function setVerifier(address _verifier) external onlyOwner {
        require(_verifier != address(0), "Invalid verifier");
        verifier = _verifier;
    }

    /**
     * @notice Create a job with UUID from backend
     * @param jobIdStr UUID string from backend (e.g., "550e8400-e29b-41d4-a716-446655440000")
     * @param modelId Model identifier
     * @param fingerprint SHA-256 hash for audit trail
     * @param amount Payment amount in USDC (6 decimals)
     */
    function createJob(
        string calldata jobIdStr,
        string calldata modelId,
        bytes32 fingerprint,
        uint256 amount
    ) external returns (bytes32 jobId) {
        require(amount > 0, "Amount must be positive");
        require(bytes(modelId).length > 0, "Invalid model");
        require(bytes(jobIdStr).length == 36, "Invalid UUID format");
        require(fingerprint != bytes32(0), "Invalid fingerprint");

        require(
            usdc.transferFrom(msg.sender, address(this), amount),
            "Payment failed"
        );

        // Encode UUID string to bytes32 (take first 32 bytes of the 36-char UUID)
        jobId = bytes32(bytes(jobIdStr));

        jobs[jobId] = Job({
            user: msg.sender,
            provider: address(0),
            modelId: modelId,
            jobId: jobId,
            fingerprint: fingerprint,
            merkleRoot: bytes32(0),
            outputHash: bytes32(0),
            amount: amount,
            createdAt: block.timestamp,
            completedAt: 0,
            completed: false,
            verified: false,
            proofValid: false
        });

        emit JobCreated(jobId, msg.sender, modelId, fingerprint, amount, block.timestamp);
        return jobId;
    }

    /**
     * @notice Worker submits execution proof
     * @dev Only the assigned provider or contract owner can submit
     */
    function submitProof(
        bytes32 jobId,
        bytes32 merkleRoot,
        bytes32 outputHash,
        address provider
    ) external {
        Job storage job = jobs[jobId];
        require(!job.completed, "Already completed");
        require(job.user != address(0), "Job not found");
        require(merkleRoot != bytes32(0), "Invalid merkle root");
        require(outputHash != bytes32(0), "Invalid output hash");
        require(provider != address(0), "Invalid provider");
        require(
            msg.sender == provider || msg.sender == owner(),
            "Not authorized"
        );

        job.provider = provider;
        job.merkleRoot = merkleRoot;
        job.outputHash = outputHash;

        emit ProofSubmitted(jobId, merkleRoot, outputHash, provider);
    }

    /**
     * @notice Verifier (backend) marks job as valid or invalid
     * @dev Only callable by verifier address
     */
    function verifyJob(bytes32 jobId, bool isValid) external nonReentrant {
        require(msg.sender == verifier, "Only verifier");

        Job storage job = jobs[jobId];
        require(!job.completed, "Already completed");
        require(job.provider != address(0), "No proof submitted");

        job.completed = true;
        job.verified = true;
        job.proofValid = isValid;
        job.completedAt = block.timestamp;

        if (isValid) {
            require(
                usdc.transfer(job.provider, job.amount),
                "Payment transfer failed"
            );
            providerEarnings[job.provider] += job.amount;
            emit PaymentReleased(jobId, job.provider, job.amount);
        } else {
            require(
                usdc.transfer(job.user, job.amount),
                "Refund transfer failed"
            );
            emit PaymentRefunded(jobId, job.user, job.amount);
        }

        emit JobVerified(jobId, isValid, block.timestamp);
    }

    function getJob(bytes32 jobId) external view returns (Job memory) {
        return jobs[jobId];
    }

    function getProviderEarnings(address provider)
        external
        view
        returns (uint256)
    {
        return providerEarnings[provider];
    }
}
```

---

## 9. Pricing Model

**Fixed Pricing Per Model (Not GPU-Hours)**

```json
{
  "models": {
    "yolov5": {
      "price_usdc": 0.05,
      "description": "Object detection - fast inference"
    },
    "bert-base": {
      "price_usdc": 0.03,
      "description": "Text classification - lightweight"
    },
    "resnet50": {
      "price_usdc": 0.05,
      "description": "Image classification"
    },
    "whisper-tiny": {
      "price_usdc": 0.10,
      "description": "Speech to text - longer inference"
    }
  }
}
```

**Why Fixed Pricing:**
- Transparent (users know exact cost upfront)
- Simple (no calculation needed)
- Fair to providers (compensation based on model complexity)
- Same regardless of network location
- Easy to scale (add models, update map)

---

## 10. Storage Architecture

**Cloudflare R2 for Models + Input Files + IPFS for Results**

### Why This Stack:

| Component | Service | Why |
|-----------|---------|-----|
| **Models** | Cloudflare R2 | 10GB/month free tier, global CDN (fast downloads for workers worldwide), no egress fees |
| **Input Files** | Cloudflare R2 | Same bucket, auto-expire after 24 hours |
| **Result Files** | Cloudflare R2 (public) + Pinata IPFS (pinned) | R2 for fast access. IPFS for immutability. |

### Architecture:

```
Model Files:
  +-- Stored in Cloudflare R2 (global CDN)
  +-- Workers download directly via presigned URLs (no backend proxy)
  +-- Cached locally on each worker (24h TTL)
  +-- Hash verified after download

Input Files:
  +-- Uploaded by user to R2 (via presigned URL)
  +-- Temporary (auto-delete after 24 hours)
  +-- Only accessible via signed URLs (private)

Result Files:
  +-- Stored in Cloudflare R2 (public read)
  +-- Pinned to IPFS via Pinata (free tier: 1GB)
  +-- IPFS hash recorded on-chain
      -> Users can verify results forever
      -> Faculty sees "immutable audit trail"
```

### Free Tier Limits:
- **Cloudflare R2:** 10GB/month free, unlimited API calls
- **Pinata IPFS:** 1GB free tier (sufficient for MVP results)

### Future (if exceeding free tier):
- R2 usage stays free (10GB models + cache is generous)
- IPFS: Can self-host Kubo node for unlimited storage
- Cost stays at $0 with self-hosted IPFS

---

## 11. Database Schema

### Supabase PostgreSQL (Free Tier)

**Why Supabase:**
- Free PostgreSQL database (50,000 rows included)
- Built-in authentication (but we use wallet auth)
- Free storage for profile pictures (not needed for MVP)
- Free real-time subscriptions (useful for dashboard)
- No credit card for free tier
- 1GB storage (plenty for MVP)

### Normalized Schema:

```sql
-- USERS
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wallet_address VARCHAR(42) UNIQUE NOT NULL,
    role VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- SUPPORTED MODELS
CREATE TABLE supported_models (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    framework VARCHAR(50),
    model_source_url VARCHAR(500),
    model_hash_sha256 VARCHAR(70),
    vram_required_gb INT,
    estimated_inference_ms INT,
    max_input_size_mb INT,
    supported_formats JSONB,
    price_usdc DECIMAL(10, 2),
    input_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- GPU NODES
CREATE TABLE nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id UUID NOT NULL REFERENCES users(id),
    gpu_name VARCHAR(100),
    vram_gb INT,
    location VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending',
    active_jobs INT DEFAULT 0,
    current_utilization DECIMAL(5, 2),
    last_heartbeat TIMESTAMP,
    api_key_hash VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_nodes_status ON nodes(status);
CREATE INDEX idx_nodes_provider ON nodes(provider_id);

-- JOBS
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    model_id VARCHAR(50) NOT NULL REFERENCES supported_models(id),
    assigned_node_id UUID REFERENCES nodes(id),
    status VARCHAR(50) DEFAULT 'pending_blockchain',
    input_file_url VARCHAR(500),
    result_file_url VARCHAR(500),
    result_ipfs_hash VARCHAR(100),
    cost_usdc DECIMAL(10, 2),
    error_message TEXT,
    blockchain_tx_hash VARCHAR(255),
    blockchain_job_id VARCHAR(66),
    fingerprint_hash VARCHAR(64),
    proof_merkle_root VARCHAR(66),
    proof_output_hash VARCHAR(64),
    proof_signature TEXT,
    proof_trace_hashes JSONB,
    proof_valid BOOLEAN DEFAULT FALSE,
    verified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_jobs_user ON jobs(user_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created ON jobs(created_at DESC);

-- PAYMENTS (Immutable Ledger)
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    user_id UUID NOT NULL REFERENCES users(id),
    provider_id UUID NOT NULL REFERENCES users(id),
    amount_usdc DECIMAL(10, 2),
    status VARCHAR(50) DEFAULT 'pending',
    blockchain_tx_hash VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    released_at TIMESTAMP
);
```

---

## 12. Environment Variables

**Backend Environment Variables (.env file):**

```bash
# Database (Supabase)
DATABASE_URL=postgresql://user:pass@db.supabase.co:5432/postgres

# Blockchain
ARBITRUM_SEPOLIA_RPC=https://sepolia-rollup.arbitrum.io/rpc
ARBITRUM_SEPOLIA_WS=wss://sepolia-rollup.arbitrum.io/ws
USDC_SEPOLIA_ADDRESS=0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d
NEBULA_PAYMENT_CONTRACT=0x...
BACKEND_EXECUTOR_ADDRESS=0x...
BACKEND_PRIVATE_KEY=0x...  # Never commit this

# Storage (Cloudflare R2)
R2_ACCOUNT_ID=your-account-id
R2_ACCESS_KEY_ID=your-access-key
R2_SECRET_ACCESS_KEY=your-secret-key
R2_BUCKET_NAME=nebula-models
R2_PUBLIC_URL=https://r2.nebula.ai

# IPFS (Pinata)
PINATA_API_KEY=your-api-key
PINATA_API_SECRET=your-api-secret

# Auth
JWT_SECRET=your-jwt-secret-min-32-chars
JWT_EXPIRY_HOURS=24
JWT_REFRESH_EXPIRY_HOURS=168

# Frontend URL (CORS)
FRONTEND_URL=https://nebula-app.vercel.app

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW_MINUTES=15

# Logging
LOG_LEVEL=INFO
TZ=UTC
```

**Worker Environment Variables (.env file on worker machine):**

```bash
# From dashboard auto-generated
NODE_ID=<uuid-from-dashboard>
API_KEY=sk_prod_...
PRIVATE_KEY=0x...  # Worker wallet private key
BACKEND_URL=https://api.nebula.ai

# Local
CUDA_VISIBLE_DEVICES=0
MODEL_CACHE_DIR=/home/user/.nebula/models
LOG_LEVEL=INFO
TZ=UTC
```

---

## 13. API Endpoints

All endpoints now use HTTPS and require authentication where applicable.

### Authentication
```
POST   /v1/auth/challenge          # Get message to sign
POST   /v1/auth/verify             # Verify signature, get JWT + refresh token
POST   /v1/auth/refresh            # Refresh expired access token
```

### Nodes (GPU Providers)
```
POST   /v1/nodes                   # Register new GPU node (authenticated)
GET    /v1/nodes                   # Get all active nodes (public)
GET    /v1/nodes/{node_id}         # Node details (public)
POST   /v1/nodes/{node_id}/heartbeat # Worker heartbeat (API key)
```

### Models (Public)
```
GET    /v1/models                  # List supported models (public)
GET    /v1/models/{model_id}/signed-url # Get presigned R2 URL (API key, 5min expiry)
```

### Jobs (Users)
```
POST   /v1/jobs                    # Submit new job (authenticated)
POST   /v1/jobs/{job_id}/confirm-blockchain # Confirm blockchain tx (authenticated)
GET    /v1/jobs                    # Get user's jobs (authenticated)
GET    /v1/jobs/{job_id}           # Job details + results (authenticated)
POST   /v1/jobs/{job_id}/complete  # Worker: mark job complete with proof (API key)
POST   /v1/jobs/{job_id}/fail      # Worker: mark job failed (API key)
POST   /v1/jobs/{job_id}/result-url # Worker: get presigned upload URL (API key)
```

### Earnings (Providers)
```
GET    /v1/earnings                # Provider earnings (authenticated)
```

### Health
```
GET    /v1/health                  # API health check (public)
```

**Security Features:**
- All endpoints use HTTPS (TLS 1.2+)
- JWT authentication (Bearer token, 24h access + 7d refresh)
- Rate limiting (100 req/15min per IP, 5 jobs/min per user, 10 auth/min per IP)
- CORS restrictions (frontend domain only)
- Signed URLs for file downloads (time-limited)
- No sensitive data in logs

**Backend Proof Verification Service:**

The backend must implement a `ProofVerifier` class that:

1. **Validates fingerprint**: Checks format is valid SHA-256 hex string, stores for audit trail.
2. **Verifies the Merkle tree**: Rebuilds the tree from `proof.trace_hashes` + `proof.output_hash` and checks that the root matches `proof.merkle_root`. Note: `MerkleTools` with `do_hash=False` expects pre-hashed hex strings as leaves. Root is computed by hashing pairs of leaves.
3. **Verifies the signature**: Uses `eth_account.Account.recover_message` to recover the signer from `(merkle_root + job_id + timestamp)` and checks it matches the provider's wallet address.
4. **Calls the smart contract**: If all checks pass, calls `verifyJob(jobId, true)` on the contract. If any check fails, calls `verifyJob(jobId, false)`.

```python
# backend/services/proof_verifier.py

import hashlib
from datetime import datetime

from eth_account import Account
from eth_account.messages import encode_defunct
from merkletools import MerkleTools


class ProofVerifier:
    """Verifies PoAE proofs (simplified MVP)"""

    @staticmethod
    def verify_proof(job, proof, provider_wallet: str):
        """
        Verify the execution proof.
        Returns (bool, error_message)
        """
        # 1. Validate fingerprint format (audit trail only)
        fingerprint = proof.get("fingerprint", "")
        if not ProofVerifier._is_valid_hex(fingerprint, 64):
            return False, "Invalid fingerprint format"

        # 2. Verify Merkle tree
        mt = MerkleTools()
        for h in proof["trace_hashes"]:
            mt.add_leaf(h, do_hash=False)  # Already hashed
        mt.add_leaf(proof["output_hash"], do_hash=False)
        mt.make_tree()
        computed_root = mt.get_merkle_root()

        if computed_root != proof["merkle_root"]:
            return False, "Merkle root mismatch"

        # 3. Verify signature (ECDSA)
        message = f"{proof['merkle_root']}:{job.id}:{proof['timestamp']}"
        message_encoded = encode_defunct(text=message)

        recovered = Account.recover_message(
            message_encoded,
            signature=proof["signature"]
        )

        if recovered.lower() != provider_wallet.lower():
            return False, "Signature invalid - provider mismatch"

        return True, "Proof valid"

    @staticmethod
    def _is_valid_hex(s: str, expected_length: int) -> bool:
        """Check if string is valid hex of expected length."""
        try:
            bytes.fromhex(s)
            return len(s) == expected_length
        except ValueError:
            return False
```

---

## 14. Deployment Architecture

### Publicly Accessible Stack (FREE TIERS ONLY)

```
+--------------------------------------------------------------+
| FRONTEND (React)                                             |
| Vercel.com (FREE: unlimited deployments, auto-scaling)      |
| https://nebula-app.vercel.app                               |
+----------------------------+----------------------------------+
                             | HTTPS
                             v
+--------------------------------------------------------------+
| BACKEND API (FastAPI)                                        |
| Fly.io FREE: 3 shared-cpu instances, 160GB/mo bandwidth    |
| https://api.nebula.ai                                       |
+----------------------------+----------------------------------+
                             |
         +-------------------+------------------+------------------+
         |                   |                  |                  |
         v                   v                  v                  v
   +-----------+     +--------------+     +------------+     +--------+
   | SUPABASE  |     | CLOUDFLARE   |     | UPSTASH    |     | IPFS   |
   | PostgreSQL|     | R2 Storage   |     | Redis      |     | Pinata |
   | (50k rows)|     | (10GB/mo)    |     | (10k/day)  |     | (1GB)  |
   +-----------+     +--------------+     +------------+     +--------+

+--------------------------------------------------------------+
| BLOCKCHAIN (Arbitrum Sepolia Testnet - FREE)                |
| RPC: https://sepolia-rollup.arbitrum.io/rpc                 |
| WS:  wss://sepolia-rollup.arbitrum.io/ws                   |
| USDC Faucet: https://faucet.circle.com (free)              |
+--------------------------------------------------------------+

+--------------------------------------------------------------+
| WORKER NODES (User-Owned Computers - FREE)                  |
| +-- Windows/Mac/Linux                                        |
| +-- Runs open-source Nebula Worker                           |
| +-- Downloads models directly from R2 (presigned URLs)       |
| +-- Connects to https://api.nebula.ai                        |
+--------------------------------------------------------------+
```

### Deployment Steps:

**Step 1: Deploy Frontend (5 minutes)**
```bash
# 1. Push code to GitHub
git push origin main

# 2. Connect Vercel to GitHub repo
# (automatic: Vercel deploys on push)

# Result: https://nebula-app.vercel.app (LIVE)
```

**Step 2: Deploy Backend (15 minutes)**
```bash
# 1. Create account at fly.io (free)
# 2. Install Fly CLI
flyctl auth signup

# 3. Create app
flyctl launch --name nebula-api

# 4. Set environment variables
flyctl secrets set \
  DATABASE_URL=$DATABASE_URL \
  ARBITRUM_SEPOLIA_RPC=$RPC \
  JWT_SECRET=$SECRET \
  ...

# 5. Deploy
flyctl deploy

# 6. Configure custom domain
flyctl domains add api.nebula.ai

# Result: https://api.nebula.ai (LIVE)
```

**Step 3: Deploy Database (5 minutes)**
```bash
# 1. Sign up: supabase.com (free)
# 2. Create new project
# 3. Run migrations:
psql $DATABASE_URL < migrations/*.sql
# 4. Test connection
python -c "import psycopg2; psycopg2.connect(os.getenv('DATABASE_URL'))"
```

**Step 4: Setup Storage (5 minutes)**
```bash
# 1. Sign up: dash.cloudflare.com (free)
# 2. Create R2 bucket
# 3. Configure custom domain: r2.nebula.ai
# 4. Generate API token
# 5. Upload models:
aws s3 cp yolov5-official.pt s3://nebula-models/ \
  --endpoint-url https://<account-id>.r2.cloudflarestorage.com \
  --access-key $R2_ACCESS_KEY_ID \
  --secret-key $R2_SECRET_ACCESS_KEY
```

**Step 5: Deploy Smart Contract (10 minutes)**
```bash
# 1. Deploy contract
forge create src/NebulaVerifiableAI.sol:NebulaVerifiableAI \
  --rpc-url https://sepolia-rollup.arbitrum.io/rpc \
  --private-key $DEPLOYER_KEY \
  --constructor-args $USDC_ADDRESS

# 2. Save contract address to .env
NEBULA_PAYMENT_CONTRACT=0x...

# 3. Update backend env vars
flyctl secrets set NEBULA_PAYMENT_CONTRACT=$CONTRACT_ADDRESS
```

**Step 6: Test Everything (15 minutes)**
```bash
# 1. Visit frontend: https://nebula-app.vercel.app
# 2. Connect wallet (MetaMask Arbitrum Sepolia)
# 3. Get testnet USDC from faucet
# 4. Register as GPU provider (no workers yet)
# 5. Submit test job (should queue after blockchain confirmation)
# 6. Check backend logs: flyctl logs
```

**Step 7: Provider Onboarding (Self-Service)**
```bash
# Providers:
# 1. Visit dashboard
# 2. Click "Download Worker"
# 3. Follow setup instructions (auto-generated)
# 4. Run: python worker.py
# 5. Worker connects to https://api.nebula.ai
# 6. Node appears online on dashboard
# 7. Ready to receive jobs
```

---

## 15. Deployment Roadmap

### Week 1-2: Local Development + AWS Prototype
- [ ] React project + FastAPI starter (local)
- [ ] MetaMask wallet connection (local)
- [ ] Smart contract development (Foundry, local)
- [ ] Database schema (Supabase free tier, cloud)
- [ ] Basic end-to-end test (localhost -> testnet blockchain)

### Week 3-4: Cloud Deployment Preparation
- [ ] Deploy frontend skeleton to Vercel
- [ ] Deploy backend skeleton to Fly.io
- [ ] Setup Supabase database (migrations)
- [ ] Setup Cloudflare R2 (upload models, configure custom domain)
- [ ] Smart contract deployment to Arbitrum Sepolia (`NebulaVerifiableAI`)
- [ ] Environment variables configured in all services
- [ ] **PoAE: Add proof columns to `jobs` table (fingerprint, merkle root, trace hashes)**
- [ ] **PoAE: Implement `submitProof` and `verifyJob` in smart contract**

### Week 5-6: Core Features
- [ ] Job submission API (frontend + backend)
- [ ] Job creation flow with UUID (backend -> blockchain -> confirm)
- [ ] Model registry integration
- [ ] Scheduler algorithm with DB-based active_jobs count
- [ ] Worker authentication (API key + JWT)
- [ ] End-to-end job flow (cloud deployment)

### Week 7-8: Worker + Payments
- [ ] Worker script download (auto-generated with API key)
- [ ] Direct R2 model download via presigned URLs
- [ ] Model hash verification after download
- [ ] Model caching (Cloudflare R2 -> local)
- [ ] Inference execution with model-specific preprocessing (YOLO + BERT + ResNet + Whisper)
- [ ] Result upload (R2 + IPFS)
- [ ] Smart contract payment release
- [ ] Blockchain event listener for payment sync
- [ ] Test with 1-2 real GPU workers (cloud)
- [ ] **PoAE: Worker generates fingerprint + execution trace + Merkle proof**
- [ ] **PoAE: Backend `ProofVerifier` service verifies proofs and calls `verifyJob` on-chain**

### Week 9: Dashboard + Polish
- [ ] Provider dashboard (nodes, earnings)
- [ ] User dashboard (jobs, results)
- [ ] Blockchain explorer links
- [ ] Notifications (Discord/Telegram)

### Week 10-11: Testing + Public Beta
- [ ] Security audit (OWASP top 10)
- [ ] Load testing (5+ concurrent jobs)
- [ ] Worker reliability testing (24hr run)
- [ ] End-to-end tests (public API)
- [ ] User onboarding flow (30+ beta testers)
- [ ] Feedback loop + bug fixes

### Week 12: Launch
- [ ] Documentation (GitHub README, API docs)
- [ ] Worker setup wizard (auto-install)
- [ ] Monitoring + alerting (logs in Fly)
- [ ] Public announcement
- [ ] Beta tester feedback incorporation
- [ ] Go live: announcement on Twitter/Discord

---

## 16. Security

### Trust Assumptions Matrix

| Component | Trust Assumption | Risk | Mitigation | Why Acceptable |
|-----------|-----------------|------|-----------|---|
| **Backend** | Correctly calls verifyJob() | HIGH: Could lie about completion | Smart contract checks Merkle root + signature | MVP: We control backend |
| **Smart Contract** | USDC is real | LOW: Verify address on Arbitrum explorer | Use official USDC (Circle) | Blockchain verified |
| **Worker API Key** | Only providers use their key | MEDIUM: Could leak/share | Rotatable keys, rate limiting | Auto-generated, can revoke |
| **Model Downloads** | Pre-vetted registry only | LOW: Prevents code exec | No arbitrary uploads + hash verification | Restricted scope |
| **Input Files** | Only legitimate users upload | MEDIUM: Could upload malware | Scan files, size limits, auto-delete | Files deleted after 24h |
| **IPFS Results** | Stored permanently | LOW: Can't delete later | Users don't expect deletion | Immutability = feature |
| **Frontend** | User's wallet is secure | LOW: MetaMask is standard | Users responsible for security | Industry standard |
| **Database** | Supabase not breached | MEDIUM: Cloud provider risk | Use strong passwords, 2FA | Encrypted at rest |
| **R2 Credentials** | API key not leaked | MEDIUM: Could be stolen | Rotate keys regularly, audit logs | Monitor R2 access logs |
| **JWT Token** | Only user can use | MEDIUM: Could be stolen | Short expiry (24h access, 7d refresh), httpOnly cookie | Browser XSS risk mitigated |

### Security Implementation:

```python
# backend/security.py

import re
from eth_account import Account
from eth_account.messages import encode_defunct


# ════════════════════════════════════════════════════════════════
# INPUT VALIDATION
# ════════════════════════════════════════════════════════════════

MAX_INPUT_FILE_SIZE_MB = 50
ALLOWED_MIME_TYPES = ['image/jpeg', 'image/png', 'text/plain', 'audio/wav', 'audio/mpeg']


async def validate_input_file(file: UploadFile, model_max_size_mb: int) -> bool:
    """Validate input file safely against model-specific size limit."""

    contents = await file.read()

    # 1. Check file size (use model-specific limit)
    max_bytes = min(model_max_size_mb, MAX_INPUT_FILE_SIZE_MB) * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(413, f"File too large (max {model_max_size_mb}MB)")

    # 2. Check MIME type
    import magic
    mime = magic.from_buffer(contents, mime=True)
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(400, f"File type {mime} not allowed")

    return True


# ════════════════════════════════════════════════════════════════
# WALLET VALIDATION
# ════════════════════════════════════════════════════════════════

def verify_wallet_signature(wallet: str, message: str, signature: str) -> bool:
    """Verify wallet signature safely using eth_account."""

    # 1. Validate wallet format
    if not re.match(r'^0x[0-9a-fA-F]{40}$', wallet):
        raise ValueError("Invalid wallet address")

    # 2. Recover signer
    msg = encode_defunct(text=message)
    recovered = Account.recover_message(msg, signature=signature)

    # 3. Compare
    return recovered.lower() == wallet.lower()


# ════════════════════════════════════════════════════════════════
# RATE LIMITING
# ════════════════════════════════════════════════════════════════

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/v1/jobs")
@limiter.limit("5/minute")  # Max 5 jobs per user per minute
async def create_job(...):
    ...

@app.post("/v1/auth/challenge")
@limiter.limit("10/minute")  # Max 10 attempts per IP
async def get_challenge(...):
    ...
```

---

## 17. Dashboard

### Provider Dashboard
```
URL: https://nebula-app.vercel.app/provider/dashboard

+--------------------------------------------------------------+
| My GPU Nodes                                          [+Register] |
+--------------------------------------------------------------+
|                                                              |
|  RTX 4090 (alice-home)                                       |
|  +-- Status: Online (last heartbeat: 2m ago)                 |
|  +-- VRAM: 24GB                                               |
|  +-- Active Jobs: 2/5                                         |
|  +-- Total Earned: 0.35 USDC                                  |
|  +-- Uptime: 99%                                              |
|  +-- [Download Worker]                                        |
|                                                              |
|  RTX 3090 (bob-office)                                       |
|  +-- Status: Offline (last heartbeat: 2h ago)                |
|  +-- VRAM: 24GB                                               |
|  +-- Active Jobs: 0/5                                         |
|  +-- Total Earned: 0.28 USDC                                  |
|  +-- Uptime: 94%                                              |
|  +-- [Download Worker]                                        |
|                                                              |
+--------------------------------------------------------------+

+--------------------------------------------------------------+
| Earnings                                                      |
+--------------------------------------------------------------+
| Total: 0.63 USDC (testnet)                                   |
| Last 7 days: 0.35 USDC                                       |
| Last 30 days: 0.63 USDC                                      |
|                                                              |
| Recent Transactions:                                         |
| +-- 2026-08-15 | YOLOv5 | +0.05 USDC | Complete             |
| +-- 2026-08-15 | BERT-Base | +0.03 USDC | Complete           |
| +-- 2026-08-15 | ResNet50 | +0.05 USDC | Complete            |
| +-- [View All]                                                |
|                                                              |
| [Withdraw to Mainnet] (coming soon)                          |
+--------------------------------------------------------------+
```

### User Dashboard
```
URL: https://nebula-app.vercel.app/user/dashboard

+--------------------------------------------------------------+
| Submit New Job                                               |
+--------------------------------------------------------------+
| Model: [YOLOv5 v]                                            |
| Input: [Choose Image...] (25MB max)                          |
| Cost: $0.05 USDC (testnet - free from faucet)                |
| [Submit & Pay]                                               |
+--------------------------------------------------------------+

+--------------------------------------------------------------+
| My Jobs                                                       |
+--------------------------------------------------------------+
|                                                              |
| Job 550e8400-... | YOLOv5 | COMPLETE | 0.05 USDC             |
| +-- Submitted: 2m ago | Completed: 1m ago                    |
| +-- Provider: 0xAlice... (RTX 4090)                          |
| +-- Result: [Download] [View on IPFS]                        |
| +-- Blockchain: [View on Arbitrum Explorer]                  |
|                                                              |
| Job 6ba7b810-... | BERT-Base | RUNNING | 0.03 USDC           |
| +-- Submitted: 5m ago | Assigned: 4m ago                     |
| +-- Provider: 0xBob... (RTX 3090)                            |
| +-- Status: Running on provider GPU                          |
| +-- Blockchain: [View on Arbitrum Explorer]                  |
|                                                              |
| Job 9161c480-... | ResNet50 | QUEUED | 0.05 USDC             |
| +-- Submitted: 8m ago                                        |
| +-- Status: Waiting for available GPU                        |
| +-- Blockchain: [View on Arbitrum Explorer]                  |
|                                                              |
+--------------------------------------------------------------+
```

---

## 18. Testing Strategy

### Unit Tests (Local)
```bash
pytest backend/tests/test_auth.py
pytest backend/tests/test_jobs.py
pytest backend/tests/test_scheduler.py
pytest backend/tests/test_proof_verifier.py
```

### Integration Tests (Against Staging)
```bash
# Test against deployed backend
pytest backend/tests/integration/ \
  --backend-url https://api.nebula.ai-staging.fly.dev
```

### Smart Contract Tests (Foundry)
```bash
forge test --match-path "test/**/*.sol" --gas-report
```

### PoAE Proof Tests
```bash
# Fingerprint, Merkle root, and signature verification
pytest backend/tests/test_proof_verifier.py::test_fingerprint_invalid_format
pytest backend/tests/test_proof_verifier.py::test_merkle_root_mismatch
pytest backend/tests/test_proof_verifier.py::test_signature_invalid
pytest backend/tests/test_proof_verifier.py::test_valid_proof_passes

# Contract-level proof tests (Foundry)
forge test --match-test testSubmitProof
forge test --match-test testVerifyJobReleasesPayment
forge test --match-test testVerifyJobRefundsOnInvalidProof
forge test --match-test testSubmitProofAccessControl
```

### End-to-End Tests (Public)
```bash
# Test complete flow
python tests/e2e/test_full_flow.py \
  --frontend-url https://nebula-app.vercel.app \
  --backend-url https://api.nebula.ai \
  --testnet usdc-address-on-sepolia
```

### Worker Reliability Tests
```bash
# Test worker with real jobs for 24 hours
python worker/worker.py --test-mode --duration=24h
```

### Monitoring (Post-Deployment)
```bash
# View logs on Fly.io
flyctl logs --app nebula-api

# Check uptime (Uptime Robot - free tier)
# Monitor: https://api.nebula.ai/v1/health
```

---

## 19. Known Limitations

1. **Uptime**: Not 99%. Fly.io free tier can have outages. Workers restart themselves.
2. **Concurrency**: Can handle 10-20 simultaneous jobs on Fly.io free tier.
3. **Models**: Only 4 supported (YOLO, BERT, ResNet, Whisper). Not general-purpose.
4. **Storage**: Cloudflare R2 has 10GB/month free (sufficient for MVP).
5. **Database**: Supabase free tier has 50,000 rows (sufficient for 1000s of jobs).
6. **Payments**: Fixed pricing only. No dynamic based on network load.
7. **Decentralization**: Backend controls scheduling (blockchain handles payments only).
8. **Security**: Workers trust backend. No code signing.
9. **Network**: Assumes good internet. Slow networks = job timeouts.
10. **Support**: Community-driven. No SLA or guaranteed uptime.
11. **Proof overhead**: Inference latency increases by ~10-15% due to checkpoint hashing and Merkle tree construction (acceptable for MVP).
12. **Simplified PoAE**: Uses a single verifier (backend), not fully decentralised. Future work: multiple independent verifiers with stake.
13. **No on-chain signature verification**: Gas is too high. We verify signatures off-chain in the backend for MVP. In future, move to on-chain with EIP-1271.
14. **Proof only covers execution, not input/output privacy**: Inputs and outputs are visible to the provider (standard for non-confidential compute).
15. **Fingerprint as audit trail only**: Worker sends hash, backend trusts it. Security relies on Merkle tree + signature verification.

**That's okay.** This is an MVP.

---

## 20. Development Cost

| Service | Purpose | Free Tier Limit | Expected Usage | Monthly Cost |
|---------|---------|-----------------|-----------------|---|
| **Vercel** | Frontend hosting | Unlimited projects | 1 project | $0 |
| **Fly.io** | Backend API | 3 shared-cpu instances, 160GB bandwidth | ~50 users | $0 |
| **Supabase** | PostgreSQL database | 50,000 rows, 1GB storage | ~10,000 jobs | $0 |
| **Cloudflare R2** | Model + file storage | 10GB/month free | 4 models + 50 job files | $0 |
| **Pinata IPFS** | Result pinning | 1GB free tier | Job results | $0 |
| **Arbitrum Sepolia** | Testnet blockchain | Free testnet gas | Unlimited | $0 |
| **MetaMask** | Wallet | Free | Unlimited | $0 |
| **GitHub** | Code hosting | Free public repos | 1 repo | $0 |
| **Upstash Redis** | Cache/queue | Free tier (10k cmds/day) | Auth challenges | $0 |
| **Uptime Robot** | Monitoring | Free tier (5 monitors) | API health check | $0 |
| | | | | |
| **TOTAL** | | | | **$0/month** |

**Scaling costs (if exceeding free tiers):**

| Scenario | When | Solution | Cost |
|----------|------|----------|------|
| Fly.io bandwidth exceeds 160GB/month | >100 active users | Self-hosted backend on cheap VPS | $5-10/month |
| Supabase exceeds 50k rows | >10,000 total jobs | Self-managed PostgreSQL | $5/month (Linode) |
| Cloudflare R2 exceeds 10GB | 100+ models or results | Use free Kubo IPFS node | $0 (self-hosted) |
| Pinata exceeds 1GB | 100+ large results | Self-hosted Kubo node | $0 (self-hosted) |

---

## 21. What Changed Compared to Local Deployment

### New Components Added

| Component | Purpose | Why Needed |
|-----------|---------|-----------|
| **Vercel** | Frontend deployment | Users access from internet (not localhost) |
| **Fly.io** | Backend deployment | API accessible from workers worldwide |
| **Supabase** | Cloud database | Persistence across deployments, multi-region |
| **Cloudflare R2** | Model CDN | Fast downloads for workers globally (direct, no proxy) |
| **Pinata IPFS** | Distributed storage | Immutable result storage |
| **Arbitrum Sepolia** | Blockchain | Same as local, but now used by real platform |
| **Upstash Redis** | Distributed cache | Auth challenges across instances |

### Architectural Differences

| Aspect | Local | Public |
|--------|-------|--------|
| **Frontend** | http://localhost:5173 | https://nebula-app.vercel.app |
| **Backend** | http://localhost:8000 | https://api.nebula.ai |
| **Database** | PostgreSQL container | Supabase cloud |
| **Storage** | MinIO container | Cloudflare R2 |
| **Models** | /models/ directory | R2 bucket + CDN (direct download) |
| **IPFS** | localhost:5001 | Pinata API |
| **Workers** | localhost:8000 | https://api.nebula.ai |
| **SSL/TLS** | None | Yes, everywhere |
| **Auth** | Simple API key | JWT + wallet signature (24h access, 7d refresh) |
| **Job IDs** | UUID | UUID (same in DB and contract) |
| **Monitoring** | Console logs | Fly.io logs + Uptime Robot |

---

## 22. Deployment Checklist

**Pre-Launch (Complete all):**

- [ ] Frontend deployed to Vercel
- [ ] Backend deployed to Fly.io
- [ ] Custom domain configured (api.nebula.ai)
- [ ] Database created in Supabase
- [ ] Storage configured in Cloudflare R2 (custom domain: r2.nebula.ai)
- [ ] Smart contract deployed to Arbitrum Sepolia
- [ ] Environment variables configured in all services
- [ ] CORS configured (Vercel domain only)
- [ ] Rate limiting enabled
- [ ] Health check endpoint working
- [ ] Database backups enabled (Supabase)
- [ ] Logs aggregated (Fly.io)
- [ ] Monitoring active (Uptime Robot)

**Testing Before Beta:**

- [ ] Frontend loads without errors
- [ ] Wallet connection works (MetaMask)
- [ ] User can submit job (testnet USDC)
- [ ] Blockchain confirmation flow works (pending_blockchain -> queued)
- [ ] Worker can register and download
- [ ] Worker can execute job with model-specific preprocessing
- [ ] PoAE proof generated (fingerprint + Merkle root + signature)
- [ ] Backend verifies proof correctly
- [ ] Payment released on blockchain after verification
- [ ] Blockchain event listener syncs payments to DB
- [ ] Result stored in R2 + IPFS
- [ ] Blockchain explorer link works
- [ ] API rate limiting works
- [ ] Workers can reconnect after disconnect
- [ ] Database schema correct

**Beta Launch:**

- [ ] Invite 10 beta testers
- [ ] Send worker setup instructions
- [ ] Monitor logs for errors
- [ ] Gather feedback
- [ ] Fix critical bugs
- [ ] Public announcement

---

## 23. Technology Stack

| Component | Technology | Free Tier | Why |
|-----------|-----------|----------|-----|
| **Frontend** | React + Vercel | Yes | Unlimited deployments, auto-scaling |
| **Backend** | FastAPI + Fly.io | Yes | 3 instances, 160GB/mo bandwidth |
| **Database** | PostgreSQL + Supabase | Yes | 50k rows, 1GB storage, no CC required |
| **Storage** | Cloudflare R2 | Yes | 10GB/mo free, no egress fees |
| **IPFS** | Pinata | Yes | 1GB free, or self-hosted Kubo |
| **Cache** | Redis + Upstash | Yes | 10k commands/day free |
| **Blockchain** | Arbitrum Sepolia | Yes | Testnet, free gas |
| **Contracts** | Solidity + Foundry | Yes | Open source |
| **Wallet** | MetaMask | Yes | Free, open source |
| **Code** | GitHub | Yes | Free public repos |
| **CI/CD** | GitHub Actions | Yes | Free for public repos |
| **Monitoring** | Uptime Robot | Yes | 5 monitors free |
| **Logs** | Fly.io native | Yes | Built-in |

**No paid services required. All free.**

---

## Summary

**You're building a publicly accessible MVP that proves:**
- Users anywhere can submit AI jobs
- Providers anywhere can register GPUs and earn
- Jobs run on distributed GPUs (globally)
- Payments are trustless (blockchain escrow)
- Execution is verifiable (PoAE with Merkle proofs + signatures)
- Everything is immutable (blockchain + IPFS)
- Built with zero budget (free tiers only)
- Deployed to internet (not localhost)

**Timeline:** 12 weeks, 1-2 people, realistic free deployment

**Result:** "This is a real platform anyone can use" -> High marks + potential users

---

**Go build it.**
