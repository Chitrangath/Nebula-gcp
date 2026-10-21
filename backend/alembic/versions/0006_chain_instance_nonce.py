"""scope signer nonce state to one concrete chain instance

Revision ID: 0006_chain_instance_nonce
Revises: 0005_runtime_hardening
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_chain_instance_nonce"
down_revision = "0005_runtime_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("signer_nonces", sa.Column("chain_instance_id", sa.String(66), nullable=True))
    op.execute("UPDATE signer_nonces SET chain_instance_id = 'legacy'")
    op.alter_column("signer_nonces", "chain_instance_id", nullable=False)
    op.drop_constraint("uq_signer_nonce_scope", "signer_nonces", type_="unique")
    op.create_unique_constraint(
        "uq_signer_nonce_scope",
        "signer_nonces",
        ["chain_id", "chain_instance_id", "signer_address"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_signer_nonce_scope", "signer_nonces", type_="unique")
    op.create_unique_constraint("uq_signer_nonce_scope", "signer_nonces", ["chain_id", "signer_address"])
    op.drop_column("signer_nonces", "chain_instance_id")
