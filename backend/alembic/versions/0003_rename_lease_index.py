"""rename_lease_index

Revision ID: 0003_rename_lease_index
Revises: 0002_data_integrity_constraints
Create Date: 2026-09-06

Renames idx_one_active_lease_per_job → idx_one_live_lease_per_job to
reflect that the partial index covers both 'active' and 'pending_chain'
statuses, not just 'active'.
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_rename_lease_index"
down_revision = "0002_data_integrity_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_one_active_lease_per_job", table_name="leases")
    op.create_index(
        "idx_one_live_lease_per_job",
        "leases",
        ["job_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'pending_chain')"),
    )


def downgrade() -> None:
    op.drop_index("idx_one_live_lease_per_job", table_name="leases")
    op.create_index(
        "idx_one_active_lease_per_job",
        "leases",
        ["job_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'pending_chain')"),
    )
