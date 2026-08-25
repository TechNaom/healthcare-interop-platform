"""De-identified store repository.

Maps to ``persistence.deid_repo`` in docs/DESIGN.md 1. Writes de-identified
resources to their own table, physically separate from PHI. There is no method
that resolves a de-identified record back to a PHI record — the separation is a
property of the API, not just the schema (docs/DATA_MODEL.md flow invariant).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hip.messaging.canonical import model as m
from hip.persistence.models import DeidResource


class DeidRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, resource: m.CanonicalResource) -> UUID:
        """Store a de-identified resource. No audit of PHI access here — the
        input is already de-identified and carries no PHI to protect."""
        row = DeidResource(
            canonical_id=resource.canonical_id,
            resource_type=type(resource).__name__,
            schema_version=resource.schema_version,
            payload=resource.model_dump(mode="json"),
        )
        self._session.add(row)
        return resource.canonical_id

    async def get(self, canonical_id: UUID) -> DeidResource | None:
        result = await self._session.execute(
            select(DeidResource).where(DeidResource.canonical_id == canonical_id)
        )
        return result.scalar_one_or_none()
