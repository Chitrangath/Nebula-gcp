"""add restart-safe proof verification claims

Revision ID: 0008_proof_verification_claims
Revises: 0007_chain_instance_events
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_proof_verification_claims"
down_revision = "0007_chain_instance_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proofs",
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="queued"),
    )
    op.add_column("proofs", sa.Column("verification_started_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE proofs SET verification_status = 'verified' WHERE valid IS NOT NULL")
    op.create_check_constraint(
        "ck_proofs_verification_status",
        "proofs",
        "verification_status IN ('queued','processing','verified')",
    )
    op.create_index("idx_proofs_verification_queue", "proofs", ["verification_status", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_proofs_verification_queue", table_name="proofs")
    op.drop_constraint("ck_proofs_verification_status", "proofs", type_="check")
    op.drop_column("proofs", "verification_started_at")
    op.drop_column("proofs", "verification_status")
