-- ═══════════════════════════════════════════════════════════════
-- Nebula AI Cloud - Initial Database Schema
-- Canonical spec: docs/NEBULA_PRD_v3.1.md Section 15
-- Run against Supabase PostgreSQL
-- ═══════════════════════════════════════════════════════════════

-- 1. USERS
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wallet_address VARCHAR(42) UNIQUE NOT NULL,
    role VARCHAR(20) CHECK (role IN ('user', 'provider')),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. SUPPORTED MODELS
CREATE TABLE IF NOT EXISTS supported_models (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    framework VARCHAR(50),
    model_source_url VARCHAR(500),
    model_hash_sha256 VARCHAR(64),
    model_version VARCHAR(50),
    preprocessing_version VARCHAR(50),
    vram_required_gb INT,
    estimated_inference_ms INT,
    max_input_size_mb INT,
    supported_formats JSONB,
    price_base_units NUMERIC(78,0) NOT NULL,
    input_type VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 3. NODES
CREATE TABLE IF NOT EXISTS nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id UUID NOT NULL REFERENCES users(id),
    gpu_name VARCHAR(100),
    vram_gb INT,
    cuda_capable BOOLEAN DEFAULT true,
    location VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'online', 'offline', 'disabled')),
    worker_signer_address VARCHAR(42),
    api_key_hash VARCHAR(64) NOT NULL,
    active_leases INT DEFAULT 0,
    last_heartbeat TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes(status);
CREATE INDEX IF NOT EXISTS idx_nodes_provider ON nodes(provider_id);

-- 4. JOBS
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    model_id VARCHAR(50) NOT NULL REFERENCES supported_models(id),
    chain_job_id VARCHAR(66) UNIQUE NOT NULL,
    assigned_node_id UUID REFERENCES nodes(id),
    current_lease_id UUID,
    status VARCHAR(50) DEFAULT 'pending_blockchain'
        CHECK (status IN (
            'pending_blockchain', 'queued', 'assigned', 'running',
            'proof_submitted', 'verifying', 'settling', 'completed',
            'retry_pending', 'attempts_exhausted', 'awaiting_timeout_refund',
            'refunded', 'expired_pre_escrow', 'failed'
        )),
    input_file_key VARCHAR(500),
    input_hash VARCHAR(64),
    result_file_key VARCHAR(500),
    result_ipfs_hash VARCHAR(100),
    expected_fingerprint VARCHAR(64),
    price_base_units NUMERIC(78,0) NOT NULL,
    error_message TEXT,
    blockchain_tx_hash VARCHAR(255),
    blockchain_escrow_amount NUMERIC(78,0),
    deadline TIMESTAMPTZ NOT NULL,
    max_attempts INT DEFAULT 3 CHECK (max_attempts > 0),
    current_attempt INT DEFAULT 0 CHECK (current_attempt >= 0),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);

-- 5. PAYMENTS
CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    user_id UUID NOT NULL REFERENCES users(id),
    provider_id UUID REFERENCES users(id),
    amount_base_units NUMERIC(78,0) NOT NULL,
    payment_type VARCHAR(20) CHECK (payment_type IN ('provider_credit', 'user_refund')),
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'credited', 'withdrawn')),
    blockchain_tx_hash VARCHAR(255) UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    credited_at TIMESTAMPTZ,
    withdrawn_at TIMESTAMPTZ
);

-- 6. AUTH CHALLENGES
CREATE TABLE IF NOT EXISTS auth_challenges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wallet_address VARCHAR(42) NOT NULL,
    nonce VARCHAR(64) UNIQUE NOT NULL,
    message TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auth_challenges_wallet ON auth_challenges(wallet_address);

-- 7. AUTH SESSIONS
CREATE TABLE IF NOT EXISTS auth_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    token_hash VARCHAR(64) UNIQUE NOT NULL,
    refresh_token_hash VARCHAR(64) UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    replaced_by_session_id UUID,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);

-- 8. LEASES
CREATE TABLE IF NOT EXISTS leases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    node_id UUID NOT NULL REFERENCES nodes(id),
    lease_id VARCHAR(66) UNIQUE NOT NULL,
    started_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    heartbeat_at TIMESTAMPTZ,
    status VARCHAR(50) DEFAULT 'pending_chain' CHECK (status IN ('pending_chain', 'active', 'expired', 'completed', 'failed')),
    tx_hash VARCHAR(66),
    nonce BIGINT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Partial unique index: at most one active or pending_chain lease per job
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_lease_per_job
    ON leases(job_id) WHERE status IN ('active', 'pending_chain');

-- 9. JOB ATTEMPTS
CREATE TABLE IF NOT EXISTS job_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    node_id UUID NOT NULL REFERENCES nodes(id),
    lease_id UUID NOT NULL REFERENCES leases(id),
    attempt_number INT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(50) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'expired')),
    error TEXT,
    fingerprint_hash VARCHAR(64),
    merkle_root VARCHAR(66),
    output_hash VARCHAR(64),
    signature TEXT,
    UNIQUE (job_id, attempt_number)
);

-- 10. PROOFS
CREATE TABLE IF NOT EXISTS proofs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_attempt_id UUID NOT NULL REFERENCES job_attempts(id),
    protocol_version INT NOT NULL DEFAULT 1,
    fingerprint_hash VARCHAR(64) NOT NULL,
    merkle_root VARCHAR(66) NOT NULL,
    output_hash VARCHAR(64) NOT NULL,
    signature TEXT NOT NULL,
    signer_address VARCHAR(42) NOT NULL,
    trace_hashes JSONB,
    proof_timestamp TIMESTAMPTZ NOT NULL,
    valid BOOLEAN,
    verification_error TEXT,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 11. CHAIN TRANSACTIONS
CREATE TABLE IF NOT EXISTS chain_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chain_id INT NOT NULL,
    contract_address VARCHAR(42) NOT NULL,
    job_id UUID REFERENCES jobs(id),
    tx_hash VARCHAR(66) UNIQUE NOT NULL,
    tx_type VARCHAR(50) NOT NULL CHECK (tx_type IN (
        'createJob', 'assignProvider', 'submitProof',
        'verifyJob', 'requestTimeoutRefund', 'withdraw'
    )),
    from_address VARCHAR(42) NOT NULL,
    to_address VARCHAR(42) NOT NULL,
    amount_base_units NUMERIC(78,0),
    block_number BIGINT,
    block_hash VARCHAR(66),
    status VARCHAR(50) DEFAULT 'submitted' CHECK (status IN ('submitted', 'confirmed', 'finalized', 'dropped')),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 12. BLOCKCHAIN EVENTS
CREATE TABLE IF NOT EXISTS blockchain_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chain_id INT NOT NULL,
    contract_address VARCHAR(42) NOT NULL,
    transaction_hash VARCHAR(66) NOT NULL,
    log_index INT NOT NULL,
    block_number BIGINT NOT NULL,
    block_hash VARCHAR(66) NOT NULL,
    event_name VARCHAR(100) NOT NULL,
    job_id UUID REFERENCES jobs(id),
    event_data JSONB,
    confirmation_status VARCHAR(50) DEFAULT 'pending' CHECK (confirmation_status IN ('pending', 'confirmed', 'finalized')),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (chain_id, contract_address, transaction_hash, log_index)
);

CREATE INDEX IF NOT EXISTS idx_blockchain_events_job ON blockchain_events(job_id);

-- ═══════════════════════════════════════════════════════════════
-- SEED DATA: Supported Models (PRD v3.1)
-- ═══════════════════════════════════════════════════════════════

INSERT INTO supported_models (id, name, framework, model_source_url, model_hash_sha256, model_version, preprocessing_version, vram_required_gb, estimated_inference_ms, max_input_size_mb, supported_formats, price_base_units, input_type)
VALUES
    ('resnet50', 'ResNet50', 'pytorch', 'https://r2.nebula.ai/resnet50-pytorch.pt', 'sha256:placeholder_resnet50', '1.0', '1.0', 2, 900, 25, '["jpg", "png"]', 50000, 'image'),
    ('yolov5', 'YOLOv5', 'pytorch', 'https://r2.nebula.ai/yolov5-official.pt', 'sha256:placeholder_yolov5', '1.0', '1.0', 4, 1500, 25, '["jpg", "png"]', 50000, 'image'),
    ('bert-base', 'BERT-Base', 'huggingface', 'https://r2.nebula.ai/bert-base-uncased.bin', 'sha256:placeholder_bert', '1.0', '1.0', 2, 800, 10, '["txt"]', 30000, 'text'),
    ('whisper-tiny', 'Whisper Tiny', 'openai', 'https://r2.nebula.ai/whisper-tiny.pt', 'sha256:placeholder_whisper', '1.0', '1.0', 3, 3000, 50, '["wav", "mp3"]', 100000, 'audio')
ON CONFLICT (id) DO NOTHING;
