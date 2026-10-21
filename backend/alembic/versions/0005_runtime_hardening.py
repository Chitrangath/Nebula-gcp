"""runtime outbox, nonce coordination, and reorg audit state

Revision ID: 0005_runtime_hardening
Revises: 0004_integration_closure
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_runtime_hardening"
down_revision = "0004_integration_closure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chain_transactions", sa.Column("transaction_payload", sa.JSON(), nullable=True))
    op.create_table(
        "signer_nonces",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("signer_address", sa.String(42), nullable=False),
        sa.Column("next_nonce", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("chain_id", "signer_address", name="uq_signer_nonce_scope"),
    )
    op.drop_constraint("ck_blockchain_events_status", "blockchain_events", type_="check")
    op.create_check_constraint(
        "ck_blockchain_events_status",
        "blockchain_events",
        "confirmation_status IN ('pending','confirmed','finalized','orphaned')",
    )
    op.create_table(
        "chain_cursors",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("contract_address", sa.String(42), nullable=False),
        sa.Column("last_scanned_block", sa.BigInteger(), nullable=False),
        sa.Column("last_scanned_block_hash", sa.String(66), nullable=False),
        sa.Column("halted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("chain_id", "contract_address", name="uq_chain_cursor_scope"),
    )
    op.create_table(
        "reconciliation_incidents",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("contract_address", sa.String(42), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("expected_block_hash", sa.String(66), nullable=False),
        sa.Column("observed_block_hash", sa.String(66), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="critical"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("details", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "chain_id",
            "contract_address",
            "block_number",
            "expected_block_hash",
            "observed_block_hash",
            name="uq_reconciliation_incident",
        ),
        sa.CheckConstraint("severity IN ('critical')", name="ck_reconciliation_incident_severity"),
        sa.CheckConstraint("status IN ('open','resolved')", name="ck_reconciliation_incident_status"),
    )


def downgrade() -> None:
    op.drop_table("reconciliation_incidents")
    op.drop_table("chain_cursors")
    op.drop_constraint("ck_blockchain_events_status", "blockchain_events", type_="check")
    op.create_check_constraint(
        "ck_blockchain_events_status",
        "blockchain_events",
        "confirmation_status IN ('pending','confirmed','finalized')",
    )
    op.drop_table("signer_nonces")
    op.drop_column("chain_transactions", "transaction_payload")
