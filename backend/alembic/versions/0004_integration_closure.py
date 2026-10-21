"""integration closure durability fields

Revision ID: 0004_integration_closure
Revises: 0003_rename_lease_index
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_integration_closure"
down_revision = "0003_rename_lease_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("result_output_hash", sa.String(64), nullable=True))
    op.add_column("jobs", sa.Column("result_size_bytes", sa.Integer(), nullable=True))
    op.add_column("proofs", sa.Column("envelope", sa.JSON(), nullable=True))
    op.create_unique_constraint("uq_proofs_job_attempt", "proofs", ["job_attempt_id"])

    op.alter_column("chain_transactions", "tx_hash", existing_type=sa.String(66), nullable=True)
    op.add_column("chain_transactions", sa.Column("nonce", sa.BigInteger(), nullable=True))
    op.add_column("chain_transactions", sa.Column("lease_id", sa.UUID(), nullable=True))
    op.add_column("chain_transactions", sa.Column("idempotency_key", sa.String(200), nullable=True))
    op.add_column("chain_transactions", sa.Column("error", sa.Text(), nullable=True))
    op.create_foreign_key("fk_chain_transactions_lease", "chain_transactions", "leases", ["lease_id"], ["id"])
    op.execute("UPDATE chain_transactions SET idempotency_key = 'legacy:' || id::text")
    op.alter_column(
        "chain_transactions",
        "idempotency_key",
        existing_type=sa.String(200),
        nullable=False,
        server_default=sa.text("gen_random_uuid()::text"),
    )
    op.create_unique_constraint("uq_chain_transactions_idempotency_key", "chain_transactions", ["idempotency_key"])
    op.drop_constraint("ck_chain_tx_status", "chain_transactions", type_="check")
    op.create_check_constraint(
        "ck_chain_tx_status",
        "chain_transactions",
        "status IN ('pending','submitted','confirmed','finalized','dropped','reverted','replaced')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_chain_tx_status", "chain_transactions", type_="check")
    op.create_check_constraint(
        "ck_chain_tx_status",
        "chain_transactions",
        "status IN ('submitted','confirmed','finalized','dropped')",
    )
    op.drop_constraint("uq_chain_transactions_idempotency_key", "chain_transactions", type_="unique")
    op.drop_constraint("fk_chain_transactions_lease", "chain_transactions", type_="foreignkey")
    op.drop_column("chain_transactions", "error")
    op.drop_column("chain_transactions", "idempotency_key")
    op.drop_column("chain_transactions", "lease_id")
    op.drop_column("chain_transactions", "nonce")
    op.alter_column("chain_transactions", "tx_hash", existing_type=sa.String(66), nullable=False)
    op.drop_constraint("uq_proofs_job_attempt", "proofs", type_="unique")
    op.drop_column("proofs", "envelope")
    op.drop_column("jobs", "result_size_bytes")
    op.drop_column("jobs", "result_output_hash")
