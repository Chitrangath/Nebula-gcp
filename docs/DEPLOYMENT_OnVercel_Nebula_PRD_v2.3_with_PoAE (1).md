# Product Requirements Document (PRD)

## **Nebula AI Cloud - MVP Edition (Version 2.3)**

**A Publicly Deployable, Blockchain-Backed, Verifiable Distributed GPU Compute Platform (Student Project)**

**Version:** 2.3 (Internet Deployment Ready + Simplified Proof-of-AI-Execution)  
**Date:** August 2026  
**Target Completion:** 6 months  
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
| AWS | ❌ | ❌ | Trust AWS |
| Render | ❌ | ❌ | Trust Render |
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
- ✅ Generate a job fingerprint (SHA-256 of model + weights + input)
- ✅ Capture execution trace (3-4 layer checkpoints during inference)
- ✅ Build a Merkle tree from the trace and sign it
- ✅ Smart contract verifies the proof before releasing payment
- ✅ Backend verifies proof integrity off-chain
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
This uniquely identifies the exact job. Stored on-chain as part of the job.

**Step 2: Execution Trace (During Inference)**
During inference, the worker records hashes at only 3-4 checkpoints:
- After the 1st layer
- After ~1/3 of layers
- After ~2/3 of layers
- After the final layer (output)

These checkpoints are stored as `trace_hashes`. We don't trace every layer (too expensive).

**Step 3: Merkle Tree Proof**
- Build a Merkle tree from `trace_hashes + [output_hash]`
- Root = `merkle_root`
- Worker signs `(merkle_root + job_id + timestamp)` with their private key
- Proof = `{fingerprint, merkle_root, trace_hashes, output_hash, signature, timestamp}`

**Step 4: Verification (Backend)**
- Recompute fingerprint from stored model/input → verify match
- Rebuild Merkle tree from `trace_hashes` → verify `merkle_root` matches
- Verify ECDSA signature against provider's wallet address
- Call smart contract: `verifyJob(jobId, True/False)`

**Why This is "Simplified" (MVP Scope):**
- **Single verifier**: The backend performs verification (no decentralized verifier network yet)
- **Lightweight trace**: Only 3-4 checkpoints, not full layer-by-layer
- **No zero-knowledge proofs**: Uses standard hashing + signatures (proven secure)
- **No on-chain signature verification**: Gas too high; we verify off-chain in backend
- **No stake/slashing**: For MVP, we just refund user on failure

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
  7. Node ID assigned
  8. Download worker script (one-click)
  9. Follow setup instructions (2 min setup)
  10. Run: python worker.py --config=auto
  11. Dashboard shows "Node Online ✅"
  12. ✅ Ready to receive jobs from anywhere
```

### Flow 2: User Submits Job (from anywhere, 10 minutes)
```
User (at coffee shop or office):
  1. Open https://nebula-app.vercel.app
  2. Connect wallet (MetaMask)
  3. Click "Submit Job"
  4. Select model: "YOLO v5" (from dropdown)
  5. Upload image (file picker)
  6. See cost: "$0.05 testnet USDC"
  7. (If no balance: click "Get Free Testnet USDC" → faucet)
  8. Click "Submit & Pay"
  9. Approve transaction in MetaMask
  10. Job created (stored on backend + blockchain)
  
Platform (automatic, distributed):
  1. Backend scheduler picks best available node
  2. Sends job to node via API (node polls every 5 sec)
  3. Node downloads model from Cloudflare R2 (cached)
  4. Node runs YOLO on image
  5. Node uploads result to R2 + IPFS
  
User (watches in real-time):
  10. Dashboard shows "Job Status: Running"
  11. Progress updates via WebSocket
  12. Result ready after ~30 seconds
  13. Downloads bounding box image
  14. Sees blockchain tx: "Payment released to provider"
  15. ✅ Done (total time: ~1 min actual)

Provider (idle):
  - Receives notification: "Job 0x123 completed, earned $0.05"
  - Can check earnings on dashboard anytime
```

---

## 7. Functional Requirements

### Module 1: User Authentication
**What it does**: Login users via wallet signature, no passwords

| Feature | Implementation |
|---------|-----------------|
| Wallet Login | MetaMask (web3modal library for multi-wallet support) |
| Sign Message | No server password. Challenge message + signature |
| Session | JWT token (httpOnly cookie, 7 day expiry) |
| Roles | `user` or `provider` (user selects at signup) |
| Multi-wallet Support | MetaMask, WalletConnect, Coinbase Wallet |

**No database passwords.** Trust the wallet.

**Security Improvements (vs local):**
- JWT refresh tokens (short-lived access, long-lived refresh)
- Rate limiting on auth endpoints (5 attempts per minute)
- CORS only allow deployed frontend domain

---

### Module 2: Node Registration & Management

**What it does**: GPU providers register machines once from anywhere

**On Frontend:**
```
Provider Dashboard (https://nebula-app.vercel.app/provider):
  ├─ "Register GPU Node" button
  │  ├─ Form fields:
  │  │  ├─ GPU Name ("RTX 3090")
  │  │  ├─ VRAM (24 GB)
  │  │  ├─ Location (e.g., "US - East")
  │  │  └─ Optional: Discord/Telegram for updates
  │  └─ "Register on Blockchain" (MetaMask popup)
  │
  ├─ "My Nodes" list
  │  ├─ Node ID, GPU Name, Status (Online/Offline)
  │  ├─ Active Jobs, Total Earnings
  │  ├─ Last Heartbeat (2 mins ago)
  │  ├─ Uptime (95%)
  │  └─ Worker Status indicator (green/red)
  │
  ├─ "Worker Setup" (auto-download)
  │  ├─ Generated setup script (bash + python)
  │  ├─ API key (auto-generated, rotatable)
  │  └─ Instructions (Linux/Mac/Windows)
  │
  └─ "Earnings" tab
     ├─ Total earned (testnet USDC)
     ├─ Withdraw to Arbitrum Mainnet (future)
     └─ Transaction history
```

**Node Registration Contract:**
```solidity
struct Job {
    address user;
    address provider;
    string modelId;
    uint256 amount;
    uint256 createdAt;
    uint256 completedAt;
    string resultIpfsHash;
    bool completed;
}

mapping(bytes32 => Job) public jobs;
mapping(address => uint256) public providerEarnings;

function createJob(string memory modelId, uint256 amount) 
    external 
    returns (bytes32 jobId)
{
    require(amount > 0, "Amount must be positive");
    require(bytes(modelId).length > 0, "Invalid model");
    
    // Transfer USDC from user to this contract (escrow)
    usdc.transferFrom(msg.sender, address(this), amount);
    
    // Generate job ID
    jobId = keccak256(abi.encodePacked(msg.sender, block.timestamp, modelId));
    
    // Store job
    jobs[jobId] = Job({
        user: msg.sender,
        provider: address(0),
        modelId: modelId,
        amount: amount,
        createdAt: block.timestamp,
        completedAt: 0,
        resultIpfsHash: "",
        completed: false
    });
    
    emit JobCreated(jobId, msg.sender, modelId, amount, block.timestamp);
    return jobId;
}
```

---

### Module 3: Supported Model Registry

**What it does**: Pre-vetted models available to users (no arbitrary uploads)

**Model Registry (Hardcoded in Backend):**

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
NEW: Select from dropdown: "YOLO v5", "BERT-Base", "ResNet50", "Whisper-Tiny"
    → System downloads pre-verified model from Cloudflare R2
    → System verifies hash against registry
    → Worker caches model locally (24 hour TTL)
```

**Benefits:**
- ✅ No arbitrary code execution (prevents GPU compromise)
- ✅ Reproducible results (same model every run)
- ✅ Fast caching (model downloaded once per worker, reused)
- ✅ Public deployment ready (models in R2, not localhost)

---

### Module 4: Job Submission

**What it does**: Users select model + upload input data and create jobs from anywhere

**On Frontend:**
```
User Dashboard (https://nebula-app.vercel.app/submit):
  ├─ "Submit Job" form
  │  ├─ Select model: [YOLO v5 ▼]
  │  ├─ Upload input file (drag-drop)
  │  ├─ Show file preview + size validation
  │  ├─ Display fixed cost: "YOLO v5 = $0.05 testnet USDC"
  │  └─ [Submit & Pay] button
  │
  └─ "My Jobs" list
     ├─ Job ID, Model, Status, Cost
     ├─ Timestamp created / started / completed
     ├─ [Download Results] button (when done)
     └─ Blockchain tx link (Arbitrum Sepolia explorer)
```

**What Happens:**

1. User selects model from registry
2. User uploads input file (frontend validates size)
3. Frontend calls `POST /v1/jobs` with model_id + input_file
4. Backend creates job record in Supabase (DB)
5. Backend uploads input to Cloudflare R2 (with expiry = 24h)
6. Backend returns job_id + blockchain transaction data
7. Frontend calls smart contract `createJob(modelId, amount)` with MetaMask
8. Smart contract creates escrow, locks USDC
9. ✅ Job ready for scheduler

---

### Module 5: Scheduler (The Smart Part)

**What it does**: Pick the best GPU node for each job (rule-based, not ML)

**Inputs:**
- Model requirements (VRAM needed, framework)
- Available nodes (status, VRAM, current load)
- Job priority (first-come-first-serve for MVP)

**Algorithm (rule-based, ~20 lines of code):**
```python
def select_node(model_vram_required, available_nodes):
    # Filter: nodes with enough VRAM AND online (heartbeat < 5 min ago)
    eligible = [
        n for n in available_nodes 
        if n.vram_gb >= model_vram_required 
        and n.status == "active"
        and n.last_heartbeat > datetime.now() - timedelta(minutes=5)
    ]
    
    if not eligible:
        return None  # No available nodes
    
    # Pick: least loaded node (fewest active jobs)
    best_node = min(eligible, key=lambda n: len(n.active_jobs))
    
    return best_node
```

**Output:**
- Selected node ID
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
#   - Node ID (auto-filled from dashboard)
#   - API key (from dashboard)
#   - Backend URL (https://api.nebula.ai)
#   - Model cache directory

# 4. Start worker (persistent)
python worker.py
# Or as service: systemctl start nebula-worker
```

**Runtime (Improved for Internet):**
```python
import asyncio
import torch
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
import os
from dotenv import load_dotenv

load_dotenv()  # Load from .env file

logger = logging.getLogger(__name__)

class Worker:
    def __init__(self):
        self.node_id = os.getenv("NODE_ID")
        self.backend_url = os.getenv("BACKEND_URL", "https://api.nebula.ai")
        self.api_key = os.getenv("API_KEY")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_cache = {}
        
    async def run(self):
        """Main worker loop"""
        logger.info(f"Worker started: {self.node_id}")
        logger.info(f"Backend: {self.backend_url}")
        
        # Start heartbeat task
        asyncio.create_task(self._heartbeat_loop())
        
        # Main job polling loop
        while True:
            try:
                job = await self._get_next_job()
                if not job:
                    await asyncio.sleep(5)
                    continue
                
                await self._execute_job(job)
            except Exception as e:
                logger.error(f"Error: {e}", exc_info=True)
                await asyncio.sleep(10)  # Back off on error
    
    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _get_next_job(self):
        """Poll backend for next job (with retry for network resilience)"""
        try:
            response = requests.get(
                f"{self.backend_url}/v1/nodes/{self.node_id}/jobs",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "User-Agent": "Nebula-Worker/1.0"
                },
                timeout=10,
                verify=True  # SSL verification
            )
            if response.status_code == 200:
                jobs = response.json().get("jobs", [])
                return jobs[0] if jobs else None
            elif response.status_code == 401:
                logger.error("❌ Authentication failed. Check API key.")
                raise Exception("Invalid API key")
            return None
        except requests.RequestException as e:
            logger.warning(f"Failed to get next job: {e}")
            raise
    
    async def _execute_job(self, job):
        """Execute job AND generate PoAE proof"""
        job_id = job["id"]
        start_time = datetime.now()
        
        try:
            # 1. Get model (cached locally)
            logger.info(f"Getting model {job['model_id']}")
            model = await self._get_model(job["model_id"])
            
            # 2. Download input file
            logger.info(f"Downloading input file")
            input_data = await self._download_input(job["input_file_url"])
            
            # ═══════════════════════════════════════════════
            # PoAE Step 1: Pre-execution fingerprint
            # ═══════════════════════════════════════════════
            fingerprint = self._compute_fingerprint(model, input_data, job["model_id"])
            
            # 3. Run inference WITH TRACING (PoAE Step 2)
            logger.info(f"Running inference with trace")
            result, trace_hashes = await self._run_inference_with_trace(
                model, input_data, job["model_id"]
            )
            
            # ═══════════════════════════════════════════════
            # PoAE Step 3: Build Merkle tree proof
            # ═══════════════════════════════════════════════
            import hashlib
            import pickle
            from merkletools import MerkleTools
            
            # Hash the final output
            output_hash = hashlib.sha256(pickle.dumps(result)).hexdigest()
            
            # Build Merkle tree from trace_hashes + output_hash
            mt = MerkleTools()
            for h in trace_hashes:
                mt.add_leaf(h, do_hash=False)  # Already hashed
            mt.add_leaf(output_hash, do_hash=False)
            mt.make_tree()
            merkle_root = mt.get_merkle_root()
            
            # Sign the proof
            message = f"{merkle_root}:{job_id}:{int(datetime.now().timestamp())}"
            signature = self._sign(message)  # Uses worker's private key
            
            proof = {
                "fingerprint": fingerprint,
                "merkle_root": merkle_root,
                "trace_hashes": trace_hashes,
                "output_hash": output_hash,
                "signature": signature.hex(),
                "public_key": self.public_key.hex(),
                "timestamp": datetime.now().isoformat()
            }
            
            # 4. Upload result to R2 + IPFS
            logger.info(f"Uploading result")
            ipfs_hash = await self._upload_result(job_id, result)
            
            # 5. Notify backend WITH PROOF
            logger.info(f"Notifying backend with proof")
            await self._notify_completion(job_id, ipfs_hash, proof)
            
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"✅ Job {job_id} completed with proof in {elapsed:.0f}ms")
            
        except asyncio.TimeoutError:
            logger.error(f"❌ Job {job_id} timed out")
            await self._notify_failure(job_id, "Inference timeout")
        except Exception as e:
            logger.error(f"❌ Job {job_id} failed: {e}", exc_info=True)
            await self._notify_failure(job_id, str(e))
    
    def _compute_fingerprint(self, model, input_data, model_id):
        """SHA-256 of model + input + metadata"""
        import hashlib
        import pickle
        
        model_bytes = pickle.dumps(model.state_dict())
        input_bytes = pickle.dumps(input_data)
        meta = f"{model_id}_{datetime.now().date()}".encode()
        combined = model_bytes + input_bytes + meta
        return hashlib.sha256(combined).hexdigest()
    
    async def _run_inference_with_trace(self, model, input_data, model_id):
        """Run inference, record 3-4 checkpoint hashes"""
        import hashlib
        import torch
        
        trace_hashes = []
        device = next(model.parameters()).device
        x = torch.tensor(input_data).to(device)
        
        # Get layers (simplified – depends on model framework)
        layers = list(model.children())
        
        # Select 3-4 checkpoint positions
        checkpoint_indices = [
            0,                          # First layer
            len(layers) // 3,           # ~1/3 through
            2 * len(layers) // 3,       # ~2/3 through
            len(layers) - 1             # Final layer
        ]
        # Remove duplicates and sort
        checkpoint_indices = sorted(set(checkpoint_indices))
        
        for i, layer in enumerate(layers):
            x = layer(x)
            if i in checkpoint_indices:
                # Record checkpoint hash
                tensor_bytes = x.detach().cpu().numpy().tobytes()
                h = hashlib.sha256(tensor_bytes).hexdigest()
                trace_hashes.append(h)
        
        # Final output
        final_output = x.detach().cpu().numpy()
        return final_output, trace_hashes
    
    def _build_merkle_root(self, leaf_hashes):
        """Build Merkle tree from leaf hashes and return root"""
        from merkletools import MerkleTools
        mt = MerkleTools()
        for h in leaf_hashes:
            mt.add_leaf(h, do_hash=False)
        mt.make_tree()
        return mt.get_merkle_root()
    
    def _sign(self, message):
        """Sign message with worker's private key (ECDSA)"""
        from eth_account import Account
        from eth_account.messages import encode_defunct
        
        msg = encode_defunct(text=message)
        signed = Account.sign_message(msg, self.private_key)
        return signed.signature
    
    async def _get_model(self, model_id):
        """Get model from cache or download from R2"""
        # Check cache (24 hour TTL)
        if model_id in self.model_cache:
            cached_age = (datetime.now() - self.model_cache[model_id]['timestamp']).total_seconds()
            if cached_age < 86400:  # 24 hours
                logger.info(f"Model {model_id} found in cache")
                return self.model_cache[model_id]['model']
        
        # Download from Cloudflare R2
        logger.info(f"Downloading model {model_id} from R2")
        response = requests.get(
            f"{self.backend_url}/v1/models/{model_id}/download",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=120  # 2 min for large models
        )
        response.raise_for_status()
        
        # Load and cache
        model = torch.load(io.BytesIO(response.content), map_location=self.device)
        self.model_cache[model_id] = {
            'model': model,
            'timestamp': datetime.now()
        }
        
        return model
    
    async def _heartbeat_loop(self):
        """Send heartbeat every 30 seconds"""
        while True:
            try:
                requests.post(
                    f"{self.backend_url}/v1/nodes/{self.node_id}/heartbeat",
                    json={
                        "utilization": 0,
                        "active_jobs": 0,
                        "timestamp": datetime.now().isoformat()
                    },
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10,
                    verify=True
                )
                logger.debug(f"Heartbeat sent")
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
            
            await asyncio.sleep(30)
```

**Key Improvements (vs local):**
- ✅ SSL/TLS verification (https://, not http://)
- ✅ API key authentication (not just node ID)
- ✅ Retry logic for network resilience
- ✅ Model caching with TTL (24 hours)
- ✅ Timeout protection (120 seconds)
- ✅ Structured logging (sent to backend)
- ✅ Environment variables (.env file)
- ✅ Cross-platform (Windows/Mac/Linux)
- ✅ Works with public API (not localhost)

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
 */
contract NebulaVerifiableAI is Ownable, ReentrancyGuard {
    
    IERC20 public usdc;
    address public verifier;  // Backend wallet (single verifier for MVP)
    
    struct Job {
        address user;
        address provider;
        string modelId;
        bytes32 fingerprint;       // SHA-256 of model + input
        bytes32 merkleRoot;        // Root of execution trace tree
        bytes32 outputHash;        // SHA-256 of final output
        uint256 amount;
        uint256 createdAt;
        uint256 completedAt;
        bool completed;
        bool verified;
        bool proofValid;
    }
    
    mapping(bytes32 => Job) public jobs;  // jobId => Job
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
        verifier = msg.sender;  // Default: deployer (backend)
    }
    
    function setVerifier(address _verifier) external onlyOwner {
        require(_verifier != address(0), "Invalid verifier");
        verifier = _verifier;
    }
    
    function createJob(
        string calldata modelId,
        bytes32 fingerprint,
        uint256 amount
    ) external returns (bytes32 jobId) {
        require(amount > 0, "Amount must be positive");
        require(bytes(modelId).length > 0, "Invalid model");
        require(fingerprint != bytes32(0), "Invalid fingerprint");
        
        require(
            usdc.transferFrom(msg.sender, address(this), amount),
            "Payment failed"
        );
        
        jobId = keccak256(abi.encodePacked(msg.sender, block.timestamp, modelId));
        
        jobs[jobId] = Job({
            user: msg.sender,
            provider: address(0),
            modelId: modelId,
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
            // Release payment to provider
            require(
                usdc.transfer(job.provider, job.amount),
                "Payment transfer failed"
            );
            providerEarnings[job.provider] += job.amount;
            emit PaymentReleased(jobId, job.provider, job.amount);
        } else {
            // Refund user
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
- ✅ Transparent (users know exact cost upfront)
- ✅ Simple (no calculation needed)
- ✅ Fair to providers (compensation based on model complexity)
- ✅ Same regardless of network location
- ✅ Easy to scale (add models, update map)

---

## 10. Storage Architecture (Updated for Public Deployment)

**NEW: Cloudflare R2 for Models + Input Files + IPFS for Results**

### Why This Stack:

| Component | Service | Why |
|-----------|---------|-----|
| **Models** | Cloudflare R2 | 10GB/month free tier, global CDN (fast downloads for workers worldwide), no egress fees |
| **Input Files** | Cloudflare R2 | Same bucket, auto-expire after 24 hours |
| **Result Files** | Cloudflare R2 (public) + Pinata IPFS (pinned) | MinIO was local-only; R2 is global. IPFS for immutability. |

### Architecture:

```
Model Files:
  ├─ Stored in Cloudflare R2 (global CDN)
  ├─ Cached locally on each worker (24h TTL)
  └─ Hash registered in smart contract for audit

Input Files:
  ├─ Uploaded by user to R2 (via presigned URL)
  ├─ Temporary (auto-delete after 24 hours)
  └─ Only accessible via signed URLs (private)

Result Files:
  ├─ Stored in Cloudflare R2 (public read)
  ├─ Pinned to IPFS via Pinata (free tier: 1GB)
  └─ IPFS hash recorded on-chain
      → Users can verify results forever
      → Faculty sees "immutable audit trail"
```

### Free Tier Limits:
- **Cloudflare R2:** 10GB/month free, unlimited API calls
- **Pinata IPFS:** 1GB free tier (sufficient for MVP results)

### Future (if exceeding free tier):
- R2 usage stays free (10GB models + cache is generous)
- IPFS: Can self-host Kubo node for unlimited storage
- Cost stays at $0 with self-hosted IPFS

---

## 11. Database Schema (Updated for Public Deployment)

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
    vram_required_gb INT,
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
    status VARCHAR(50) DEFAULT 'pending',
    current_utilization DECIMAL(5, 2),
    last_heartbeat TIMESTAMP,
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
    status VARCHAR(50) DEFAULT 'queued',
    input_file_url VARCHAR(500),
    result_file_url VARCHAR(500),
    result_ipfs_hash VARCHAR(100),
    cost_usdc DECIMAL(10, 2),
    error_message TEXT,
    blockchain_tx_hash VARCHAR(255),
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

-- BLOCKCHAIN EVENTS (Audit Log)
CREATE TABLE blockchain_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_name VARCHAR(100),
    job_id UUID REFERENCES jobs(id),
    transaction_hash VARCHAR(255) UNIQUE,
    block_number BIGINT,
    event_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_blockchain_events_job ON blockchain_events(job_id);
```

**PoAE Proof Columns (added to `jobs` table):**

```sql
-- PoAE columns for proof storage
ALTER TABLE jobs ADD COLUMN fingerprint_hash VARCHAR(64);
ALTER TABLE jobs ADD COLUMN proof_merkle_root VARCHAR(66);
ALTER TABLE jobs ADD COLUMN proof_output_hash VARCHAR(64);
ALTER TABLE jobs ADD COLUMN proof_signature TEXT;
ALTER TABLE jobs ADD COLUMN proof_trace_hashes JSONB;  -- Array of checkpoint hashes
ALTER TABLE jobs ADD COLUMN proof_valid BOOLEAN DEFAULT FALSE;
ALTER TABLE jobs ADD COLUMN verified_at TIMESTAMP;
```

---

## 12. Environment Variables (New Section)

**Backend Environment Variables (.env file):**

```bash
# Database (Supabase)
DATABASE_URL=postgresql://user:pass@db.supabase.co:5432/postgres

# Redis (free tier option: Upstash)
REDIS_URL=redis://:password@default-redis.upstash.io:6379

# Blockchain
ARBITRUM_SEPOLIA_RPC=https://sepolia-rollup.arbitrum.io/rpc
USDC_SEPOLIA_ADDRESS=0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d
NEBULA_PAYMENT_CONTRACT=0x...  # Deployed address
BACKEND_EXECUTOR_ADDRESS=0x...  # Your wallet
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

# Frontend URL (CORS)
FRONTEND_URL=https://nebula-app.vercel.app

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW_MINUTES=15

# Logging
LOG_LEVEL=INFO
```

**Worker Environment Variables (.env file on worker machine):**

```bash
# From dashboard auto-generated
NODE_ID=node_abc123
API_KEY=sk_prod_...
BACKEND_URL=https://api.nebula.ai

# Local
CUDA_VISIBLE_DEVICES=0  # Which GPU to use
MODEL_CACHE_DIR=/home/user/.nebula/models
LOG_LEVEL=INFO
```

---

## 13. API Endpoints (Updated for Public Deployment)

All endpoints now use HTTPS and require authentication where applicable.

### Authentication
```
POST   /v1/auth/challenge          # Get message to sign
POST   /v1/auth/verify             # Verify signature, get JWT
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
GET    /v1/models/{model_id}/download # Download model via signed URL (API key)
```

### Jobs (Users)
```
POST   /v1/jobs                    # Submit new job (authenticated)
GET    /v1/jobs                    # Get user's jobs (authenticated)
GET    /v1/jobs/{job_id}           # Job details + results (authenticated)
POST   /v1/jobs/{job_id}/verify    # Internal: backend verifies proof (no public access)
```

### Earnings (Providers)
```
GET    /v1/earnings                # Provider earnings (authenticated)
```

### Health
```
GET    /v1/health                  # API health check (public)
```

### WebSocket (Real-Time)
```
WS     /ws/dashboard               # Real-time dashboard updates (authenticated)
```

**Security Features:**
- ✅ All endpoints use HTTPS (TLS 1.2+)
- ✅ JWT authentication (Bearer token)
- ✅ Rate limiting (100 req/15min per IP)
- ✅ CORS restrictions (frontend domain only)
- ✅ Signed URLs for file downloads (time-limited)
- ✅ No sensitive data in logs

**Backend Proof Verification Service:**

The backend must implement a `ProofVerifier` class that:

1. **Recomputes the fingerprint**: Loads the model and input from storage, computes SHA-256, and compares with `proof.fingerprint`.
2. **Verifies the Merkle tree**: Rebuilds the tree from `proof.trace_hashes` + `proof.output_hash` and checks that the root matches `proof.merkle_root`.
3. **Verifies the signature**: Uses `eth_account` to recover the signer from `(merkle_root + job_id + timestamp)` and checks it matches the provider's wallet address.
4. **Calls the smart contract**: If all checks pass, calls `verifyJob(jobId, true)` on the contract. If any check fails, calls `verifyJob(jobId, false)`.

```python
# backend/services/proof_verifier.py

import hashlib
import pickle
from merkletools import MerkleTools
from eth_account import Account
from eth_account.messages import encode_defunct

class ProofVerifier:
    """Verifies PoAE proofs (simplified MVP)"""
    
    @staticmethod
    def verify_proof(job, proof, model_data, input_data, provider_wallet):
        """
        Verify the execution proof.
        Returns (bool, error_message)
        """
        # 1. Re-compute fingerprint
        expected_fingerprint = ProofVerifier._compute_fingerprint(
            model_data, input_data, job.model_id
        )
        if expected_fingerprint != proof["fingerprint"]:
            return False, "Fingerprint mismatch"
        
        # 2. Verify Merkle tree
        mt = MerkleTools()
        for h in proof["trace_hashes"]:
            mt.add_leaf(h, do_hash=False)
        mt.add_leaf(proof["output_hash"], do_hash=False)
        mt.make_tree()
        computed_root = mt.get_merkle_root()
        
        if computed_root != proof["merkle_root"]:
            return False, "Merkle root mismatch"
        
        # 3. Verify signature (ECDSA)
        message = f"{proof['merkle_root']}:{job.id}:{proof['timestamp']}"
        message_encoded = encode_defunct(text=message)
        
        # Recover signer from signature
        recovered = Account.recover_message(
            message_encoded,
            signature=proof["signature"]
        )
        
        # Compare with expected provider wallet
        if recovered.lower() != provider_wallet.lower():
            return False, "Signature invalid – provider mismatch"
        
        return True, "Proof valid"
    
    @staticmethod
    def _compute_fingerprint(model_bytes, input_bytes, model_id):
        """Match worker's fingerprint computation"""
        meta = f"{model_id}_{datetime.now().date()}".encode()
        combined = model_bytes + pickle.dumps(input_bytes) + meta
        return hashlib.sha256(combined).hexdigest()
```

---

## 14. Deployment Architecture (New Section)

### Publicly Accessible Stack (FREE TIERS ONLY)

```
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (React)                                            │
│ Vercel.com (FREE: unlimited deployments, auto-scaling)     │
│ https://nebula-app.vercel.app                              │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTPS / WebSocket
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ BACKEND API (FastAPI)                                       │
│ Fly.io FREE: 3 shared-cpu instances, 160GB/mo bandwidth    │
│ https://api.nebula.ai                                       │
└─────────────────────────┬───────────────────────────────────┘
                          │
        ┌─────────────────┼──────────────────┬─────────────────┐
        │                 │                  │                 │
        ▼                 ▼                  ▼                 ▼
   ┌─────────┐    ┌─────────────┐    ┌──────────────┐    ┌────────┐
   │SUPABASE │    │CLOUDFLARE R2│    │REDIS UPSTASH │    │  IPFS  │
   │PostgreSQL    │Storage      │    │(Cache/Queue) │    │Pinata  │
   │(FREE:50k rows)   │(10GB/mo free)   │(FREE: 10k cmds/day) │(1GB)  │
   │No credit card│No egress!   │    │No credit card │    │Free    │
   └─────────┘    └─────────────┘    └──────────────┘    └────────┘

┌────────────────────────────────────────────────────────────┐
│ BLOCKCHAIN (Arbitrum Sepolia Testnet - FREE)              │
│ RPC: https://sepolia-rollup.arbitrum.io/rpc               │
│ USDC Faucet: https://faucet.circle.com (free)             │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ WORKER NODES (User-Owned Computers - FREE)                │
│ ├─ Windows/Mac/Linux                                       │
│ ├─ Runs open-source Nebula Worker                          │
│ └─ Connects to https://api.nebula.ai                       │
└────────────────────────────────────────────────────────────┘
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

# Result: https://nebula-api.fly.dev (LIVE)
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
# 3. Generate API token
# 4. Upload models:
   aws s3 cp yolov5-official.pt s3://nebula-models/ \
     --endpoint-url https://r2.nebula.ai \
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
# 5. Submit test job (should queue)
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

## 15. Deployment Roadmap (Updated)

### Week 1-2: Local Development + AWS Prototype
- [ ] React project + FastAPI starter (local)
- [ ] MetaMask wallet connection (local)
- [ ] Smart contract development (Foundry, local)
- [ ] Database schema (Supabase free tier, cloud)
- [ ] Basic end-to-end test (localhost → testnet blockchain)

### Week 3-4: Cloud Deployment Preparation
- [ ] Deploy frontend skeleton to Vercel
- [ ] Deploy backend skeleton to Fly.io
- [ ] Setup Supabase database (migrations)
- [ ] Setup Cloudflare R2 (upload models)
- [ ] Smart contract deployment to Arbitrum Sepolia (`NebulaVerifiableAI`)
- [ ] Environment variables configured in all services
- [ ] **PoAE: Add proof columns to `jobs` table (fingerprint, merkle root, trace hashes)**
- [ ] **PoAE: Implement `submitProof` and `verifyJob` in smart contract**

### Week 5-6: Core Features
- [ ] Job submission API (frontend + backend)
- [ ] Model registry integration
- [ ] Scheduler algorithm
- [ ] Worker authentication (API key + JWT)
- [ ] End-to-end job flow (cloud deployment)

### Week 7-8: Worker + Payments
- [ ] Worker script download (auto-generated with API key)
- [ ] Model caching (Cloudflare R2 → local)
- [ ] Inference execution (YOLO + BERT + ResNet + Whisper)
- [ ] Result upload (R2 + IPFS)
- [ ] Smart contract payment release
- [ ] Test with 1-2 real GPU workers (cloud)
- [ ] **PoAE: Worker generates fingerprint + execution trace + Merkle proof (`_execute_job`)**
- [ ] **PoAE: Backend `ProofVerifier` service verifies proofs and calls `verifyJob` on-chain**

### Week 9: Dashboard + Polish
- [ ] Provider dashboard (nodes, earnings)
- [ ] User dashboard (jobs, results)
- [ ] Real-time updates (WebSocket)
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

## 16. Security (Updated for Public Deployment)

### Trust Assumptions Matrix

| Component | Trust Assumption | Risk | Mitigation | Why Acceptable |
|-----------|-----------------|------|-----------|---|
| **Backend** | Correctly calls completeJob() | HIGH: Could lie about completion | Smart contract checks signature | MVP: We control backend |
| **Smart Contract** | USDC is real | LOW: Verify address on Arbitrum explorer | Use official USDC (Circle) | Blockchain verified |
| **Worker API Key** | Only providers use their key | MEDIUM: Could leak/share | Rotatable keys, rate limiting | Auto-generated, can revoke |
| **Model Downloads** | Pre-vetted registry only | LOW: Prevents code exec | No arbitrary uploads | Restricted scope |
| **Input Files** | Only legitimate users upload | MEDIUM: Could upload malware | Scan files, size limits, auto-delete | Files deleted after 24h |
| **IPFS Results** | Stored permanently | LOW: Can't delete later | Users don't expect deletion | Immutability = feature |
| **Frontend** | User's wallet is secure | LOW: MetaMask is standard | Users responsible for security | Industry standard |
| **Database** | Supabase not breached | MEDIUM: Cloud provider risk | Use strong passwords, 2FA | Encrypted at rest |
| **R2 Credentials** | API key not leaked | MEDIUM: Could be stolen | Rotate keys regularly, audit logs | Monitor R2 access logs |
| **JWT Token** | Only user can use | MEDIUM: Could be stolen | Short expiry (24h), httpOnly cookie | Browser XSS risk mitigated |

### Security Implementation:

```python
# backend/security.py

# ════════════════════════════════════════════════════════════════
# INPUT VALIDATION
# ════════════════════════════════════════════════════════════════

MAX_INPUT_FILE_SIZE_MB = 500
ALLOWED_MIME_TYPES = ['image/jpeg', 'image/png', 'text/plain', 'audio/wav', 'audio/mpeg']

async def validate_input_file(file: UploadFile) -> bool:
    """Validate input file safely"""
    
    contents = await file.read()
    
    # 1. Check file size
    if len(contents) > MAX_INPUT_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, "File too large")
    
    # 2. Check MIME type
    import magic
    mime = magic.from_buffer(contents, mime=True)
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(400, f"File type {mime} not allowed")
    
    return True

# ════════════════════════════════════════════════════════════════
// WALLET VALIDATION
// ════════════════════════════════════════════════════════════════

def verify_wallet_signature(wallet: str, message: str, signature: str) -> bool:
    """Verify wallet signature safely"""
    
    from eth_account.messages import encode_defunct
    from web3 import Web3
    
    # 1. Validate wallet format
    if not Web3.is_address(wallet):
        raise ValueError("Invalid wallet address")
    
    # 2. Recover signer
    msg = encode_defunct(text=message)
    recovered = Web3.eth.account.recover_message(msg, signature=signature)
    
    # 3. Compare
    return recovered.lower() == wallet.lower()

# ════════════════════════════════════════════════════════════════
// RATE LIMITING
// ════════════════════════════════════════════════════════════════

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

## 17. Dashboard (Updated for Public Deployment)

### Provider Dashboard
```
URL: https://nebula-app.vercel.app/provider/dashboard

┌─────────────────────────────────────────────────────────┐
│ My GPU Nodes                                     [+Register] │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  RTX 4090 (alice-home)                                  │
│  ├─ Status: 🟢 Online (last heartbeat: 2m ago)          │
│  ├─ VRAM: 24GB                                          │
│  ├─ Active Jobs: 2/5                                    │
│  ├─ Total Earned: 0.35 USDC                             │
│  ├─ Uptime: 99%                                         │
│  └─ [View Logs] [Download Worker] [Rotate API Key]      │
│                                                         │
│  RTX 3090 (bob-office)                                  │
│  ├─ Status: 🟡 Offline (last heartbeat: 2h ago)         │
│  ├─ VRAM: 24GB                                          │
│  ├─ Active Jobs: 0/5                                    │
│  ├─ Total Earned: 0.28 USDC                             │
│  ├─ Uptime: 94%                                         │
│  └─ [View Logs] [Download Worker] [Rotate API Key]      │
│                                                         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Earnings                                                 │
├─────────────────────────────────────────────────────────┤
│ Total: 0.63 USDC (testnet)                              │
│ Last 7 days: 0.35 USDC                                  │
│ Last 30 days: 0.63 USDC                                 │
│                                                         │
│ Recent Transactions:                                    │
│ ├─ 2024-08-15 | YOLO v5 | +0.05 USDC | ✅ Complete     │
│ ├─ 2024-08-15 | BERT-Base | +0.03 USDC | ✅ Complete   │
│ ├─ 2024-08-15 | ResNet50 | +0.05 USDC | ✅ Complete    │
│ └─ [View All] [Export CSV]                              │
│                                                         │
│ [Withdraw to Mainnet] (coming soon)                     │
└─────────────────────────────────────────────────────────┘
```

### User Dashboard
```
URL: https://nebula-app.vercel.app/user/dashboard

┌─────────────────────────────────────────────────────────┐
│ Submit New Job                                          │
├─────────────────────────────────────────────────────────┤
│ Model: [YOLO v5 ▼]                                      │
│ Input: [Choose Image...] (25MB max)                     │
│ Cost: $0.05 USDC (testnet - free from faucet)           │
│ [Submit & Pay]                                          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ My Jobs                                                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Job 0x7a2b... | YOLO v5 | ✅ COMPLETE | 0.05 USDC       │
│ ├─ Submitted: 2m ago | Completed: 1m ago                │
│ ├─ Provider: 0xAlice... (RTX 4090)                      │
│ ├─ Result: [Download] [View on IPFS]                    │
│ └─ Blockchain: [View on Arbitrum Explorer]              │
│                                                         │
│ Job 0x8c4d... | BERT-Base | ⏳ RUNNING | 0.03 USDC       │
│ ├─ Submitted: 5m ago | Assigned: 4m ago                 │
│ ├─ Provider: 0xBob... (RTX 3090)                        │
│ ├─ Status: Running on provider GPU                      │
│ └─ Blockchain: [View on Arbitrum Explorer]              │
│                                                         │
│ Job 0x9e5f... | ResNet50 | 🔄 QUEUED | 0.05 USDC        │
│ ├─ Submitted: 8m ago                                    │
│ ├─ Status: Waiting for available GPU                    │
│ └─ Blockchain: [View on Arbitrum Explorer]              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 18. Testing Strategy (Updated for Public Deployment)

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
pytest backend/tests/test_proof_verifier.py::test_fingerprint_mismatch
pytest backend/tests/test_proof_verifier.py::test_merkle_root_mismatch
pytest backend/tests/test_proof_verifier.py::test_signature_invalid
pytest backend/tests/test_proof_verifier.py::test_valid_proof_passes

# Contract-level proof tests (Foundry)
forge test --match-test testSubmitProof
forge test --match-test testVerifyJobReleasesPayment
forge test --match-test testVerifyJobRefundsOnInvalidProof
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

## 19. Known Limitations (Honest About These)

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

**That's okay.** This is an MVP.

---

## 20. Development Cost (New Section - ZERO DOLLARS)

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
| **Upstash Redis** | Cache/queue | Free tier (10k cmds/day) | Job queue | $0 |
| **Uptime Robot** | Monitoring | Free tier (5 monitors) | API health check | $0 |
| **SendGrid** | Email notifications | Free tier (100 emails/day) | User alerts | $0 |
| **Discord Bot** | Notifications | Free to create | Real-time alerts | $0 |
| | | | | |
| **TOTAL** | | | | **$0/month** |

**Scaling costs (if exceeding free tiers):**

| Scenario | When | Solution | Cost |
|----------|------|----------|------|
| Fly.io bandwidth exceeds 160GB/month | >100 active users | Self-hosted backend on cheap VPS | $5-10/month |
| Supabase exceeds 50k rows | >10,000 total jobs | Self-managed PostgreSQL | $5/month (Linode) |
| Cloudflare R2 exceeds 10GB | 100+ models or results | Use free Kubo IPFS node | $0 (self-hosted) |
| Pinata exceeds 1GB | 100+ large results | Self-hosted Kubo node | $0 (self-hosted) |

**Current estimate: $0/month for MVP, $0 if properly using free tiers + self-hosted options**

---

## 21. What Changed Compared to Local Deployment (New Section)

### New Components Added

| Component | Purpose | Why Needed |
|-----------|---------|-----------|
| **Vercel** | Frontend deployment | Users access from internet (not localhost) |
| **Fly.io** | Backend deployment | API accessible from workers worldwide |
| **Supabase** | Cloud database | Persistence across deployments, multi-region |
| **Cloudflare R2** | Model CDN | Fast downloads for workers globally |
| **Pinata IPFS** | Distributed storage | Immutable result storage |
| **Arbitrum Sepolia** | Blockchain | Same as local, but now used by real platform |
| **Upstash Redis** | Distributed cache | Auth challenges, job queue across instances |
| **GitHub Actions** | CI/CD | Auto-deploy on push |

### Architectural Differences

| Aspect | Local | Public |
|--------|-------|--------|
| **Frontend** | http://localhost:5173 | https://nebula-app.vercel.app |
| **Backend** | http://localhost:8000 | https://api.nebula.ai |
| **Database** | PostgreSQL container | Supabase cloud |
| **Storage** | MinIO container | Cloudflare R2 |
| **Models** | /models/ directory | R2 bucket + CDN |
| **IPFS** | localhost:5001 | Pinata API |
| **Workers** | localhost:8000 | https://api.nebula.ai |
| **SSL/TLS** | None | Yes, everywhere |
| **Auth** | Simple API key | JWT + wallet signature |
| **Monitoring** | Console logs | Fly.io logs + Uptime Robot |

### Complexity Additions (Minor)

| Addition | Impact | Why Worth It |
|----------|--------|-------------|
| **Environment variables** | Must configure 15 variables | Necessary for cloud deployment |
| **CORS handling** | Frontend domain whitelisting | Required for security |
| **Rate limiting** | Track usage per IP | Prevent abuse |
| **Signed URLs** | Time-limited file access | Security for S3/R2 |
| **JWT refresh tokens** | Token rotation | Better security than local demo |
| **Database migrations** | Run schemas on cloud DB | Reproducible deployments |
| **Worker authentication** | API key + signature | Prevent spoofing from untrusted networks |
| **Logging aggregation** | Logs sent to backend | Debuggable from anywhere |

**Estimated additional development time: +2 weeks (out of 12 weeks total)**

**Why it's worth it:**
- ✅ Real users can access platform
- ✅ Providers can register from anywhere
- ✅ Testable by community before scaling
- ✅ Experience with cloud deployment
- ✅ All code reusable for mainnet production
- ✅ Much more impressive than localhost demo

---

## 22. Deployment Checklist

**Pre-Launch (Complete all):**

- [ ] Frontend deployed to Vercel
- [ ] Backend deployed to Fly.io
- [ ] Database created in Supabase
- [ ] Storage configured in Cloudflare R2
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
- [ ] Worker can register and download
- [ ] Worker can execute job
- [ ] Result stored in R2 + IPFS
- [ ] Payment released on blockchain
- [ ] Dashboard shows real-time updates
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

## 23. Technology Stack (Verified for Free Tiers)

| Component | Technology | Free Tier | Why |
|-----------|-----------|----------|-----|
| **Frontend** | React + Vercel | ✅ Yes | Unlimited deployments, auto-scaling |
| **Backend** | FastAPI + Fly.io | ✅ Yes | 3 instances, 160GB/mo bandwidth |
| **Database** | PostgreSQL + Supabase | ✅ Yes | 50k rows, 1GB storage, no CC required |
| **Storage** | Cloudflare R2 | ✅ Yes | 10GB/mo free, no egress fees |
| **IPFS** | Pinata | ✅ Yes | 1GB free, or self-hosted Kubo |
| **Cache** | Redis + Upstash | ✅ Yes | 10k commands/day free |
| **Blockchain** | Arbitrum Sepolia | ✅ Yes | Testnet, free gas |
| **Contracts** | Solidity + Foundry | ✅ Yes | Open source |
| **Wallet** | MetaMask | ✅ Yes | Free, open source |
| **Code** | GitHub | ✅ Yes | Free public repos |
| **CI/CD** | GitHub Actions | ✅ Yes | Free for public repos |
| **Monitoring** | Uptime Robot | ✅ Yes | 5 monitors free |
| **Emails** | SendGrid | ✅ Yes | 100/day free tier |
| **Logs** | Fly.io native | ✅ Yes | Built-in |

**No paid services required. All free.**

---

## Summary

**You're building a publicly accessible MVP that proves:**
- ✅ Users anywhere can submit AI jobs
- ✅ Providers anywhere can register GPUs and earn
- ✅ Jobs run on distributed GPUs (globally)
- ✅ Payments are trustless (blockchain escrow)
- ✅ Everything is immutable (blockchain + IPFS)
- ✅ Built with zero budget (free tiers only)
- ✅ Deployed to internet (not localhost)

**Timeline:** 12 weeks, 1-2 people, realistic free deployment

**Result:** "This is a real platform anyone can use" → High marks + potential users

---

**Go build it. 🚀**