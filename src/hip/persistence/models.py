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

from sqlalchemy import DateTime, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class PhiResource(Base):
    """A stored canonical resource.

    ``payload_ciphertext`` holds the canonical document **encrypted** by the
    KeyManager (HIPAA 164.312(a)(2)(iv)) — Postgres only ever sees ciphertext.
    The relational spine (id/type/version) stays clear for lookup and indexing.
    """

    __tablename__ = "phi_resources"

    canonical_id: Mapped[UUID] = mapped_column(primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(64), index=True)
    schema_version: Mapped[str] = mapped_column(String(32))
    payload_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
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


class DeidResource(Base):
    """A de-identified resource, kept in a SEPARATE store from PHI.

    Deliberately carries NO column linking back to the source PHI record — a
    reverse path would defeat de-identification (docs/DATA_MODEL.md flow
    invariant). ``id`` is the de-identified instance's own fresh canonical_id.
    """

    __tablename__ = "deid_resources"

    canonical_id: Mapped[UUID] = mapped_column(primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(64), index=True)
    schema_version: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PhiIdentifierIndex(Base):
    """Blind-index rows for exact-match search over encrypted PHI.

    Each stored resource's identifiers are recorded here as keyed HMAC digests
    (``identifier_hash``) so search never touches the encrypted payload and the
    plaintext identifier is never stored in a searchable column
    (docs/DATA_MODEL.md; hip.security.blind_index).
    """

    __tablename__ = "phi_identifier_index"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    canonical_id: Mapped[UUID] = mapped_column(index=True)
    resource_type: Mapped[str] = mapped_column(String(64), index=True)
    identifier_hash: Mapped[str] = mapped_column(String(64), index=True)


class DeadLetterRow(Base):
    """An unprocessable inbound message (docs/DATA_MODEL.md DeadLetterMessage).

    Classified PHI: the raw HL7 payload can contain PHI, so ``raw_ciphertext`` is
    encrypted by the KeyManager just like the PHI store — this is NOT a debug log.
    The metadata columns stay clear for triage/reprocessing.
    """

    __tablename__ = "dead_letter_messages"

    dead_letter_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    failure_stage: Mapped[str] = mapped_column(
        String(16), index=True
    )  # parse/validate/transform/persist
    failure_reason_code: Mapped[str] = mapped_column(String(64))
    failure_reason_detail: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)  # MSH-3/4
    message_control_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    raw_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)  # encrypted raw HL7 (PHI)
