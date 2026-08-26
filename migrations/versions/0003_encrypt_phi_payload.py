"""encrypt PHI at rest: phi_resources.payload (JSONB) -> payload_ciphertext (BYTEA)

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-25

PHI is now encrypted by the KeyManager before storage, so the plaintext JSONB
column is replaced by a ciphertext BYTEA column. No production data exists yet;
on a fresh database the table is empty when this runs.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("phi_resources", "payload")
    op.add_column(
        "phi_resources",
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("phi_resources", "payload_ciphertext")
    op.add_column(
        "phi_resources",
        sa.Column("payload", postgresql.JSONB(), nullable=False),
    )
