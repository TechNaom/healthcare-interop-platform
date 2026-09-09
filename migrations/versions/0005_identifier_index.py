"""blind-index table: phi_identifier_index

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phi_identifier_index",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("identifier_hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_phi_identifier_index_canonical_id", "phi_identifier_index", ["canonical_id"])
    op.create_index(
        "ix_phi_identifier_index_resource_type", "phi_identifier_index", ["resource_type"]
    )
    op.create_index("ix_phi_identifier_index_hash", "phi_identifier_index", ["identifier_hash"])


def downgrade() -> None:
    op.drop_table("phi_identifier_index")
