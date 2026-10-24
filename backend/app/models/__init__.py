import uuid

from sqlalchemy import (
    JSON,
    UUID,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_address = Column(String(42), unique=True, nullable=False)
    role = Column(String(20))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    nodes = relationship("Node", back_populates="provider")
    jobs = relationship("Job", back_populates="user")
    sessions = relationship("AuthSession", back_populates="user")
    payments_as_user = relationship("Payment", foreign_keys="Payment.user_id", back_populates="user")
    payments_as_provider = relationship("Payment", foreign_keys="Payment.provider_id", back_populates="provider")

    __table_args__ = (CheckConstraint("role IN ('user', 'provider')", name="ck_users_role"),)


class SupportedModel(Base):
    __tablename__ = "supported_models"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    framework = Column(String(50))
    model_source_url = Column(String(500))
    model_hash_sha256 = Column(String(64))
    model_version = Column(String(50))
    preprocessing_version = Column(String(50))
    vram_required_gb = Column(Integer)
    estimated_inference_ms = Column(Integer)
    max_input_size_mb = Column(Integer)
    supported_formats = Column(JSON)
    price_base_units = Column(Numeric(78, 0), nullable=False)
    input_type = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Node(Base):
    __tablename__ = "nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    gpu_name = Column(String(100))
    vram_gb = Column(Integer)
    cuda_capable = Column(Boolean, default=True)
    supports_bert = Column(Boolean, default=False, server_default="false", nullable=False)
    location = Column(String(100))
    status = Column(String(50), default="pending")
    worker_signer_address = Column(String(42))
    api_key_hash = Column(String(64), nullable=False)
    active_leases = Column(Integer, default=0)
    last_heartbeat = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    provider = relationship("User", back_populates="nodes")
    leases = relationship("Lease", back_populates="node")
    job_attempts = relationship("JobAttempt", back_populates="node")

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'online', 'offline', 'disabled')", name="ck_nodes_status"),
        Index("idx_nodes_status", "status"),
        Index("idx_nodes_provider", "provider_id"),
    )


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    model_id = Column(String(50), ForeignKey("supported_models.id"), nullable=False)
    chain_job_id = Column(String(66), unique=True, nullable=False)
    assigned_node_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id"))
    current_lease_id = Column(UUID(as_uuid=True))
    status = Column(String(50), default="pending_blockchain")
    input_file_key = Column(String(500))
    input_hash = Column(String(64))
    result_file_key = Column(String(500))
    result_output_hash = Column(String(64))
    result_size_bytes = Column(Integer)
    result_ipfs_hash = Column(String(100))
    expected_fingerprint = Column(String(64))
    price_base_units = Column(Numeric(78, 0), nullable=False)
    error_message = Column(Text)
    blockchain_tx_hash = Column(String(255))
    blockchain_escrow_amount = Column(Numeric(78, 0))
    deadline = Column(DateTime(timezone=True), nullable=False)
    max_attempts = Column(Integer, default=3)
    current_attempt = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    user = relationship("User", back_populates="jobs")
    model = relationship("SupportedModel")
    assigned_node = relationship("Node", foreign_keys=[assigned_node_id])
    payments = relationship("Payment", back_populates="job")
    leases = relationship("Lease", back_populates="job")
    job_attempts = relationship("JobAttempt", back_populates="job")
    chain_transactions = relationship("ChainTransaction", back_populates="job")
    blockchain_events = relationship("BlockchainEvent", back_populates="job")

    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'pending_blockchain', 'queued', 'assigned', 'running', "
            "'proof_submitted', 'verifying', 'settling', 'completed', "
            "'retry_pending', 'attempts_exhausted', 'awaiting_timeout_refund', "
            "'refunded', 'expired_pre_escrow', 'failed'"
            ")",
            name="ck_jobs_status",
        ),
        CheckConstraint("max_attempts > 0", name="ck_jobs_max_attempts"),
        CheckConstraint("current_attempt >= 0", name="ck_jobs_current_attempt"),
        Index("idx_jobs_user", "user_id"),
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_created", "created_at"),
    )


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    amount_base_units = Column(Numeric(78, 0), nullable=False)
    payment_type = Column(String(20))
    status = Column(String(50), default="pending")
    blockchain_tx_hash = Column(String(255), unique=True)
    withdrawal_tx_hash = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    credited_at = Column(DateTime(timezone=True))
    withdrawn_at = Column(DateTime(timezone=True))

    job = relationship("Job", back_populates="payments")
    user = relationship("User", foreign_keys=[user_id], back_populates="payments_as_user")
    provider = relationship("User", foreign_keys=[provider_id], back_populates="payments_as_provider")

    __table_args__ = (
        CheckConstraint("payment_type IN ('provider_credit', 'user_refund')", name="ck_payments_type"),
        CheckConstraint("status IN ('pending', 'credited', 'withdrawn')", name="ck_payments_status"),
        Index("idx_payments_withdrawal_tx", "withdrawal_tx_hash"),
    )


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_address = Column(String(42), nullable=False)
    nonce = Column(String(64), unique=True, nullable=False)
    message = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("idx_auth_challenges_wallet", "wallet_address"),)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)
    refresh_token_hash = Column(String(64), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))
    replaced_by_session_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="sessions")

    __table_args__ = (Index("idx_auth_sessions_user", "user_id"),)


class Lease(Base):
    __tablename__ = "leases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    node_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id"), nullable=False)
    lease_id = Column(String(66), unique=True, nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    heartbeat_at = Column(DateTime(timezone=True))
    status = Column(String(50), default="pending_chain")
    tx_hash = Column(String(66))
    nonce = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("Job", back_populates="leases")
    node = relationship("Node", back_populates="leases")
    job_attempts = relationship("JobAttempt", back_populates="lease")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_chain', 'active', 'expired', 'completed', 'failed')",
            name="ck_leases_status",
        ),
    )


class JobAttempt(Base):
    __tablename__ = "job_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    node_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id"), nullable=False)
    lease_id = Column(UUID(as_uuid=True), ForeignKey("leases.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    status = Column(String(50), default="running")
    error = Column(Text)
    fingerprint_hash = Column(String(64))
    merkle_root = Column(String(66))
    output_hash = Column(String(64))
    signature = Column(Text)

    job = relationship("Job", back_populates="job_attempts")
    node = relationship("Node", back_populates="job_attempts")
    lease = relationship("Lease", back_populates="job_attempts")
    proof = relationship("Proof", back_populates="job_attempt", uselist=False)

    __table_args__ = (
        UniqueConstraint("job_id", "attempt_number", name="uq_job_attempt_number"),
        CheckConstraint("status IN ('running', 'completed', 'failed', 'expired')", name="ck_job_attempts_status"),
    )


class Proof(Base):
    __tablename__ = "proofs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_attempt_id = Column(UUID(as_uuid=True), ForeignKey("job_attempts.id"), nullable=False)
    protocol_version = Column(Integer, nullable=False, default=1)
    fingerprint_hash = Column(String(64), nullable=False)
    merkle_root = Column(String(66), nullable=False)
    output_hash = Column(String(64), nullable=False)
    signature = Column(Text, nullable=False)
    signer_address = Column(String(42), nullable=False)
    trace_hashes = Column(JSON)
    envelope = Column(JSON)
    proof_timestamp = Column(DateTime(timezone=True), nullable=False)
    valid = Column(Boolean)
    verification_status = Column(String(20), nullable=False, default="queued", server_default="queued")
    verification_started_at = Column(DateTime(timezone=True))
    verification_error = Column(Text)
    verified_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job_attempt = relationship("JobAttempt", back_populates="proof")

    __table_args__ = (
        UniqueConstraint("job_attempt_id", name="uq_proofs_job_attempt"),
        CheckConstraint(
            "verification_status IN ('queued', 'processing', 'verified')",
            name="ck_proofs_verification_status",
        ),
        Index("idx_proofs_verification_queue", "verification_status", "created_at"),
    )


class ChainTransaction(Base):
    __tablename__ = "chain_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_id = Column(Integer, nullable=False)
    chain_instance_id = Column(String(66))
    contract_address = Column(String(42), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"))
    tx_hash = Column(String(66))
    tx_type = Column(String(50), nullable=False)
    from_address = Column(String(42), nullable=False)
    to_address = Column(String(42), nullable=False)
    nonce = Column(Integer)
    lease_id = Column(UUID(as_uuid=True), ForeignKey("leases.id"))
    idempotency_key = Column(
        String(200),
        unique=True,
        nullable=False,
        default=lambda: uuid.uuid4().hex,
        server_default=func.gen_random_uuid(),
    )
    error = Column(Text)
    transaction_payload = Column(JSON)
    amount_base_units = Column(Numeric(78, 0))
    block_number = Column(Integer)
    block_hash = Column(String(66))
    status = Column(String(50), default="submitted")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("Job", back_populates="chain_transactions")

    __table_args__ = (
        UniqueConstraint("chain_instance_id", "tx_hash", name="uq_chain_transactions_hash_instance"),
        CheckConstraint(
            "tx_type IN ('createJob', 'assignProvider', 'submitProof', "
            "'verifyJob', 'requestTimeoutRefund', 'withdraw')",
            name="ck_chain_tx_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'submitted', 'confirmed', 'finalized', 'dropped', 'reverted', 'replaced')",
            name="ck_chain_tx_status",
        ),
    )


class SignerNonce(Base):
    """Durable nonce allocator for one backend signer on one chain."""

    __tablename__ = "signer_nonces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_id = Column(Integer, nullable=False)
    chain_instance_id = Column(String(66), nullable=False)
    signer_address = Column(String(42), nullable=False)
    next_nonce = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("chain_id", "chain_instance_id", "signer_address", name="uq_signer_nonce_scope"),
    )


class BlockchainEvent(Base):
    __tablename__ = "blockchain_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_id = Column(Integer, nullable=False)
    chain_instance_id = Column(String(66), nullable=False, default="legacy")
    contract_address = Column(String(42), nullable=False)
    transaction_hash = Column(String(66), nullable=False)
    log_index = Column(Integer, nullable=False)
    block_number = Column(Integer, nullable=False)
    block_hash = Column(String(66), nullable=False)
    event_name = Column(String(100), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"))
    event_data = Column(JSON)
    confirmation_status = Column(String(50), default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("Job", back_populates="blockchain_events")

    __table_args__ = (
        UniqueConstraint(
            "chain_id",
            "chain_instance_id",
            "contract_address",
            "transaction_hash",
            "log_index",
            name="uq_blockchain_events_identity",
        ),
        CheckConstraint(
            "confirmation_status IN ('pending', 'confirmed', 'finalized', 'orphaned')",
            name="ck_blockchain_events_status",
        ),
        Index("idx_blockchain_events_job", "job_id"),
    )


class ChainCursor(Base):
    """Persistent event-poller progress and safety stop for a deployment."""

    __tablename__ = "chain_cursors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_id = Column(Integer, nullable=False)
    chain_instance_id = Column(String(66), nullable=False)
    contract_address = Column(String(42), nullable=False)
    last_scanned_block = Column(Integer, nullable=False)
    last_scanned_block_hash = Column(String(66), nullable=False)
    halted = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("chain_id", "chain_instance_id", "contract_address", name="uq_chain_cursor_scope"),
    )


class ReconciliationIncident(Base):
    """Durable evidence for finalized-chain contradictions."""

    __tablename__ = "reconciliation_incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_id = Column(Integer, nullable=False)
    chain_instance_id = Column(String(66), nullable=False)
    contract_address = Column(String(42), nullable=False)
    block_number = Column(Integer, nullable=False)
    expected_block_hash = Column(String(66), nullable=False)
    observed_block_hash = Column(String(66), nullable=False)
    severity = Column(String(20), nullable=False, default="critical")
    status = Column(String(20), nullable=False, default="open")
    details = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "chain_id",
            "chain_instance_id",
            "contract_address",
            "block_number",
            "expected_block_hash",
            "observed_block_hash",
            name="uq_reconciliation_incident",
        ),
        CheckConstraint("severity IN ('critical')", name="ck_reconciliation_incident_severity"),
        CheckConstraint("status IN ('open', 'resolved')", name="ck_reconciliation_incident_status"),
    )
