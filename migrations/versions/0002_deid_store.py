"""de-identified store: deid_resources

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deid_resources",
        sa.Column("canonical_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_deid_resources_resource_type", "deid_resources", ["resource_type"])


def downgrade() -> None:
    op.drop_table("deid_resources")
