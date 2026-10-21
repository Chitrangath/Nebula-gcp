"""scope outbox and event identity to one concrete chain instance

Revision ID: 0007_chain_instance_events
Revises: 0006_chain_instance_nonce
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_chain_instance_events"
down_revision = "0006_chain_instance_nonce"
branch_labels = None
depends_on = None


def _add_legacy_instance(table: str, *, nullable: bool = False) -> None:
    op.add_column(table, sa.Column("chain_instance_id", sa.String(66), nullable=True))
    op.execute(f"UPDATE {table} SET chain_instance_id = 'legacy'")
    if not nullable:
        op.alter_column(table, "chain_instance_id", nullable=False)


def upgrade() -> None:
    _add_legacy_instance("chain_transactions", nullable=True)
    op.drop_constraint("chain_transactions_tx_hash_key", "chain_transactions", type_="unique")
    op.create_unique_constraint(
        "uq_chain_transactions_hash_instance", "chain_transactions", ["chain_instance_id", "tx_hash"]
    )

    _add_legacy_instance("blockchain_events")
    # Alembic-created schemas use the explicit name from migration 0001, while
    # older test schemas created from SQLAlchemy metadata use PostgreSQL's
    # generated name.  Both histories are supported without requiring a reset.
    op.execute("ALTER TABLE blockchain_events DROP CONSTRAINT IF EXISTS uq_blockchain_events_identity")
    op.execute(
        "ALTER TABLE blockchain_events DROP CONSTRAINT IF EXISTS "
        "blockchain_events_chain_id_contract_address_transaction_has_key"
    )
    op.create_unique_constraint(
        "uq_blockchain_events_identity",
        "blockchain_events",
        ["chain_id", "chain_instance_id", "contract_address", "transaction_hash", "log_index"],
    )

    _add_legacy_instance("chain_cursors")
    op.drop_constraint("uq_chain_cursor_scope", "chain_cursors", type_="unique")
    op.create_unique_constraint(
        "uq_chain_cursor_scope", "chain_cursors", ["chain_id", "chain_instance_id", "contract_address"]
    )

    _add_legacy_instance("reconciliation_incidents")
    op.drop_constraint("uq_reconciliation_incident", "reconciliation_incidents", type_="unique")
    op.create_unique_constraint(
        "uq_reconciliation_incident",
        "reconciliation_incidents",
        [
            "chain_id",
            "chain_instance_id",
            "contract_address",
            "block_number",
            "expected_block_hash",
            "observed_block_hash",
        ],
    )


def downgrade() -> None:
    op.drop_constraint("uq_reconciliation_incident", "reconciliation_incidents", type_="unique")
    op.create_unique_constraint(
        "uq_reconciliation_incident",
        "reconciliation_incidents",
        ["chain_id", "contract_address", "block_number", "expected_block_hash", "observed_block_hash"],
    )
    op.drop_column("reconciliation_incidents", "chain_instance_id")

    op.drop_constraint("uq_chain_cursor_scope", "chain_cursors", type_="unique")
    op.create_unique_constraint("uq_chain_cursor_scope", "chain_cursors", ["chain_id", "contract_address"])
    op.drop_column("chain_cursors", "chain_instance_id")

    op.drop_constraint("uq_blockchain_events_identity", "blockchain_events", type_="unique")
    op.create_unique_constraint(
        "uq_blockchain_events_identity",
        "blockchain_events",
        ["chain_id", "contract_address", "transaction_hash", "log_index"],
    )
    op.drop_column("blockchain_events", "chain_instance_id")

    op.drop_constraint("uq_chain_transactions_hash_instance", "chain_transactions", type_="unique")
    op.create_unique_constraint("chain_transactions_tx_hash_key", "chain_transactions", ["tx_hash"])
    op.drop_column("chain_transactions", "chain_instance_id")
