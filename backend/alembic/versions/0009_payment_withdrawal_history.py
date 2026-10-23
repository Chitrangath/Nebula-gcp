"""add provider withdrawal history

Revision ID: 0009_payment_withdrawal_history
Revises: 0008_proof_verification_claims
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_payment_withdrawal_history"
down_revision = "0008_proof_verification_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("withdrawal_tx_hash", sa.String(255), nullable=True))
    op.create_index("idx_payments_withdrawal_tx", "payments", ["withdrawal_tx_hash"])


def downgrade() -> None:
    op.drop_index("idx_payments_withdrawal_tx", table_name="payments")
    op.drop_column("payments", "withdrawal_tx_hash")
