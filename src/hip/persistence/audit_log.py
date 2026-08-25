"""Append-only audit log writer (HIPAA 164.312(b)).

Maps to ``persistence.audit_log`` in docs/DESIGN.md 1. Records who accessed or
mutated which PHI resource and when. The API is insert-only by construction —
there is no update or delete method — so the append-only guarantee is a property
of the code surface, not merely a convention (DB-level grants reinforce it in a
later phase). Never write PHI *values* into an audit entry; ``detail`` is for
control-plane context only.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from hip.persistence.models import AuditEvent


class AuditLog:
    """Insert-only audit writer bound to a session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        action: str,
        resource_type: str,
        actor: str,
        resource_id: UUID | None = None,
        detail: str | None = None,
    ) -> AuditEvent:
        """Append one audit entry (not committed here; the caller's unit of work
        commits, so the audit row and the data change share one transaction)."""
        event = AuditEvent(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor=actor,
            detail=detail,
        )
        self._session.add(event)
        return event
