"""dead-letter store: dead_letter_messages (encrypted raw payload)

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dead_letter_messages",
        sa.Column("dead_letter_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_stage", sa.String(16), nullable=False),
        sa.Column("failure_reason_code", sa.String(64), nullable=False),
        sa.Column("failure_reason_detail", sa.String(1024), nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("message_control_id", sa.String(64), nullable=True),
        sa.Column("raw_ciphertext", sa.LargeBinary(), nullable=False),
    )
    op.create_index("ix_dead_letter_received_at", "dead_letter_messages", ["received_at"])
    op.create_index("ix_dead_letter_failure_stage", "dead_letter_messages", ["failure_stage"])
    op.create_index(
        "ix_dead_letter_message_control_id", "dead_letter_messages", ["message_control_id"]
    )


def downgrade() -> None:
    op.drop_table("dead_letter_messages")
