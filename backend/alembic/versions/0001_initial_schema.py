"""initial_schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-03

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # 1. users
    # ──────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("wallet_address", sa.String(42), nullable=False, unique=True),
        sa.Column("role", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('user', 'provider')", name="ck_users_role"),
    )

    # ──────────────────────────────────────────────
    # 2. supported_models
    # ──────────────────────────────────────────────
    op.create_table(
        "supported_models",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("framework", sa.String(50), nullable=True),
        sa.Column("model_source_url", sa.String(500), nullable=True),
        sa.Column("model_hash_sha256", sa.String(64), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("preprocessing_version", sa.String(50), nullable=True),
        sa.Column("vram_required_gb", sa.Integer(), nullable=True),
        sa.Column("estimated_inference_ms", sa.Integer(), nullable=True),
        sa.Column("max_input_size_mb", sa.Integer(), nullable=True),
        sa.Column("supported_formats", sa.JSON(), nullable=True),
        sa.Column("price_base_units", sa.Numeric(78, 0), nullable=False),
        sa.Column("input_type", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ──────────────────────────────────────────────
    # 3. nodes
    # ──────────────────────────────────────────────
    op.create_table(
        "nodes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "provider_id",
            sa.UUID(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("gpu_name", sa.String(100), nullable=True),
        sa.Column("vram_gb", sa.Integer(), nullable=True),
        sa.Column("cuda_capable", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("location", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), server_default=sa.text("'pending'")),
        sa.Column("worker_signer_address", sa.String(42), nullable=True),
        sa.Column("api_key_hash", sa.String(64), nullable=False),
        sa.Column("active_leases", sa.Integer(), server_default=sa.text("0")),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('pending', 'online', 'offline', 'disabled')",
            name="ck_nodes_status",
        ),
    )
    op.create_index("idx_nodes_status", "nodes", ["status"])
    op.create_index("idx_nodes_provider", "nodes", ["provider_id"])

    # ──────────────────────────────────────────────
    # 4. jobs
    # ──────────────────────────────────────────────
    op.create_table(
        "jobs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "model_id",
            sa.String(50),
            sa.ForeignKey("supported_models.id"),
            nullable=False,
        ),
        sa.Column("chain_job_id", sa.String(66), nullable=False, unique=True),
        sa.Column(
            "assigned_node_id",
            sa.UUID(),
            sa.ForeignKey("nodes.id"),
            nullable=True,
        ),
        sa.Column("current_lease_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(50), server_default=sa.text("'pending_blockchain'")),
        sa.Column("input_file_key", sa.String(500), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("result_file_key", sa.String(500), nullable=True),
        sa.Column("result_ipfs_hash", sa.String(100), nullable=True),
        sa.Column("expected_fingerprint", sa.String(64), nullable=True),
        sa.Column("price_base_units", sa.Numeric(78, 0), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("blockchain_tx_hash", sa.String(255), nullable=True),
        sa.Column("blockchain_escrow_amount", sa.Numeric(78, 0), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3")),
        sa.Column("current_attempt", sa.Integer(), server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ("
            "'pending_blockchain', 'queued', 'assigned', 'running', "
            "'proof_submitted', 'verifying', 'settling', 'completed', "
            "'retry_pending', 'attempts_exhausted', 'awaiting_timeout_refund', "
            "'refunded', 'expired_pre_escrow', 'failed'"
            ")",
            name="ck_jobs_status",
        ),
        sa.CheckConstraint("max_attempts > 0", name="ck_jobs_max_attempts"),
        sa.CheckConstraint("current_attempt >= 0", name="ck_jobs_current_attempt"),
    )
    op.create_index("idx_jobs_user", "jobs", ["user_id"])
    op.create_index("idx_jobs_status", "jobs", ["status"])
    op.create_index("idx_jobs_created", "jobs", [sa.text("created_at DESC")])

    # ──────────────────────────────────────────────
    # 5. payments
    # ──────────────────────────────────────────────
    op.create_table(
        "payments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "job_id",
            sa.UUID(),
            sa.ForeignKey("jobs.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "provider_id",
            sa.UUID(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("amount_base_units", sa.Numeric(78, 0), nullable=False),
        sa.Column("payment_type", sa.String(20), nullable=True),
        sa.Column("status", sa.String(50), server_default=sa.text("'pending'")),
        sa.Column("blockchain_tx_hash", sa.String(255), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("credited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "payment_type IN ('provider_credit', 'user_refund')",
            name="ck_payments_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'credited', 'withdrawn')",
            name="ck_payments_status",
        ),
    )

    # ──────────────────────────────────────────────
    # 6. auth_challenges
    # ──────────────────────────────────────────────
    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("wallet_address", sa.String(42), nullable=False),
        sa.Column("nonce", sa.String(64), nullable=False, unique=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_auth_challenges_wallet", "auth_challenges", ["wallet_address"])

    # ──────────────────────────────────────────────
    # 7. auth_sessions
    # ──────────────────────────────────────────────
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_session_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_auth_sessions_user", "auth_sessions", ["user_id"])

    # ──────────────────────────────────────────────
    # 8. leases
    # ──────────────────────────────────────────────
    op.create_table(
        "leases",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "job_id",
            sa.UUID(),
            sa.ForeignKey("jobs.id"),
            nullable=False,
        ),
        sa.Column(
            "node_id",
            sa.UUID(),
            sa.ForeignKey("nodes.id"),
            nullable=False,
        ),
        sa.Column("lease_id", sa.String(66), nullable=False, unique=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(50), server_default=sa.text("'pending_chain'")),
        sa.Column("tx_hash", sa.String(66), nullable=True),
        sa.Column("nonce", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('pending_chain', 'active', 'expired', 'completed', 'failed')",
            name="ck_leases_status",
        ),
    )
    # Partial unique index: at most one pending_chain or active lease per job
    op.create_index(
        "idx_one_active_lease_per_job",
        "leases",
        ["job_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'pending_chain')"),
    )

    # ──────────────────────────────────────────────
    # 9. job_attempts
    # ──────────────────────────────────────────────
    op.create_table(
        "job_attempts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "job_id",
            sa.UUID(),
            sa.ForeignKey("jobs.id"),
            nullable=False,
        ),
        sa.Column(
            "node_id",
            sa.UUID(),
            sa.ForeignKey("nodes.id"),
            nullable=False,
        ),
        sa.Column(
            "lease_id",
            sa.UUID(),
            sa.ForeignKey("leases.id"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(50), server_default=sa.text("'running'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("fingerprint_hash", sa.String(64), nullable=True),
        sa.Column("merkle_root", sa.String(66), nullable=True),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.UniqueConstraint("job_id", "attempt_number", name="uq_job_attempt_number"),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'expired')",
            name="ck_job_attempts_status",
        ),
        sa.CheckConstraint("attempt_number > 0", name="ck_job_attempts_attempt_number"),
    )

    # ──────────────────────────────────────────────
    # 10. proofs
    # ──────────────────────────────────────────────
    op.create_table(
        "proofs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "job_attempt_id",
            sa.UUID(),
            sa.ForeignKey("job_attempts.id"),
            nullable=False,
        ),
        sa.Column("protocol_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("fingerprint_hash", sa.String(64), nullable=False),
        sa.Column("merkle_root", sa.String(66), nullable=False),
        sa.Column("output_hash", sa.String(64), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("signer_address", sa.String(42), nullable=False),
        sa.Column("trace_hashes", sa.JSON(), nullable=True),
        sa.Column("proof_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=True),
        sa.Column("verification_error", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ──────────────────────────────────────────────
    # 11. chain_transactions
    # ──────────────────────────────────────────────
    op.create_table(
        "chain_transactions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("contract_address", sa.String(42), nullable=False),
        sa.Column(
            "job_id",
            sa.UUID(),
            sa.ForeignKey("jobs.id"),
            nullable=True,
        ),
        sa.Column("tx_hash", sa.String(66), nullable=False, unique=True),
        sa.Column("tx_type", sa.String(50), nullable=False),
        sa.Column("from_address", sa.String(42), nullable=False),
        sa.Column("to_address", sa.String(42), nullable=False),
        sa.Column("amount_base_units", sa.Numeric(78, 0), nullable=True),
        sa.Column("block_number", sa.BigInteger(), nullable=True),
        sa.Column("block_hash", sa.String(66), nullable=True),
        sa.Column("status", sa.String(50), server_default=sa.text("'submitted'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "tx_type IN ('createJob', 'assignProvider', 'submitProof', "
            "'verifyJob', 'requestTimeoutRefund', 'withdraw')",
            name="ck_chain_tx_type",
        ),
        sa.CheckConstraint(
            "status IN ('submitted', 'confirmed', 'finalized', 'dropped')",
            name="ck_chain_tx_status",
        ),
    )

    # ──────────────────────────────────────────────
    # 12. blockchain_events
    # ──────────────────────────────────────────────
    op.create_table(
        "blockchain_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("contract_address", sa.String(42), nullable=False),
        sa.Column("transaction_hash", sa.String(66), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("block_hash", sa.String(66), nullable=False),
        sa.Column("event_name", sa.String(100), nullable=False),
        sa.Column(
            "job_id",
            sa.UUID(),
            sa.ForeignKey("jobs.id"),
            nullable=True,
        ),
        sa.Column("event_data", sa.JSON(), nullable=True),
        sa.Column("confirmation_status", sa.String(50), server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "chain_id",
            "contract_address",
            "transaction_hash",
            "log_index",
            name="uq_blockchain_events_identity",
        ),
        sa.CheckConstraint(
            "confirmation_status IN ('pending', 'confirmed', 'finalized')",
            name="ck_blockchain_events_status",
        ),
    )
    op.create_index("idx_blockchain_events_job", "blockchain_events", ["job_id"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("blockchain_events")
    op.drop_table("chain_transactions")
    op.drop_table("proofs")
    op.drop_table("job_attempts")
    op.drop_index("idx_one_active_lease_per_job", table_name="leases")
    op.drop_table("leases")
    op.drop_table("auth_sessions")
    op.drop_table("auth_challenges")
    op.drop_table("payments")
    op.drop_table("jobs")
    op.drop_table("nodes")
    op.drop_table("supported_models")
    op.drop_table("users")
