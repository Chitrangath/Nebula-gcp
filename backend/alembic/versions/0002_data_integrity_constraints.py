"""data_integrity_constraints

Revision ID: 0002_data_integrity_constraints
Revises: 0001_initial_schema
Create Date: 2026-09-03

Monetary columns — justification:
  supported_models.price_base_units > 0   — every listed model must have a non-zero price
  jobs.price_base_units > 0               — every job is created against a priced model
  jobs.blockchain_escrow_amount IS NULL OR > 0  — NULL means not yet escrowed; once set it must be positive
  payments.amount_base_units > 0          — every payment record is a positive transfer
  chain_transactions.amount_base_units IS NULL OR >= 0  — NULL for non-value txns (submitProof);
                                                          0 allowed for zero-value contract calls
"""

from alembic import op

revision = "0002_data_integrity_constraints"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Monetary constraints ──────────────────────────
    op.create_check_constraint(
        "ck_supported_models_price_positive",
        "supported_models",
        "price_base_units > 0",
    )
    op.create_check_constraint(
        "ck_jobs_price_positive",
        "jobs",
        "price_base_units > 0",
    )
    op.create_check_constraint(
        "ck_jobs_escrow_positive_or_null",
        "jobs",
        "blockchain_escrow_amount IS NULL OR blockchain_escrow_amount > 0",
    )
    op.create_check_constraint(
        "ck_payments_amount_positive",
        "payments",
        "amount_base_units > 0",
    )
    op.create_check_constraint(
        "ck_chain_tx_amount_non_negative_or_null",
        "chain_transactions",
        "amount_base_units IS NULL OR amount_base_units >= 0",
    )

    # ── Wallet address canonical lowercase + format ───
    op.create_check_constraint(
        "ck_users_wallet_lowercase_hex",
        "users",
        "wallet_address ~ '^0x[0-9a-f]{40}$'",
    )
    op.create_check_constraint(
        "ck_auth_challenges_wallet_lowercase_hex",
        "auth_challenges",
        "wallet_address ~ '^0x[0-9a-f]{40}$'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_auth_challenges_wallet_lowercase_hex", "auth_challenges")
    op.drop_constraint("ck_users_wallet_lowercase_hex", "users")
    op.drop_constraint("ck_chain_tx_amount_non_negative_or_null", "chain_transactions")
    op.drop_constraint("ck_payments_amount_positive", "payments")
    op.drop_constraint("ck_jobs_escrow_positive_or_null", "jobs")
    op.drop_constraint("ck_jobs_price_positive", "jobs")
    op.drop_constraint("ck_supported_models_price_positive", "supported_models")
