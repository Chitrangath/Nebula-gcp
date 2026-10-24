"""Advertise BERT capability without routing text jobs to legacy workers."""

import sqlalchemy as sa
from alembic import op

revision = "0010_node_bert_capability"
down_revision = "0009_payment_withdrawal_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("supports_bert", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("nodes", "supports_bert")
