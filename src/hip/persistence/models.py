"""SQLAlchemy ORM tables (docs/DATA_MODEL.md "Data classification & storage").

Two tables for this slice:

* ``phi_resources`` — canonical instances (Patient/Encounter/Order/Observation/
  DeadLetter). Relational spine (id, type, version, timestamps) plus a JSONB
  ``payload`` for the full canonical document — matches DATA_MODEL's "relational
  + JSONB" choice and lets the schema evolve without a migration per field.
  Classified PHI: encrypted at rest and access-audited (encryption lands with
  the KeyManager phase; the audit trail is here now).
* ``audit_events`` — append-only record of every PHI access/mutation (HIPAA
  164.312(b)). There is deliberately no update/delete code path.

Store separation (PHI vs de-identified vs audit) is enforced at the repository/
grant layer; for this build all three tables share one database with distinct
tables, and the schema stays queryable enough for later anomaly detection
(ADR-009).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class PhiResource(Base):
    """A stored canonical resource. ``payload`` is the canonical model as JSON."""

    __tablename__ = "phi_resources"

    canonical_id: Mapped[UUID] = mapped_column(primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(64), index=True)
    schema_version: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditEvent(Base):
    """Append-only audit entry. Written only by the persistence layer; no
    update/delete path exists in code (immutability is also enforced by DB
    grants in a later phase)."""

    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    action: Mapped[str] = mapped_column(String(16), index=True)  # create/read/update/delete
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(128), index=True)  # who (system/user)
    detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
