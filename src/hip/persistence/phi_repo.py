"""PHI repository — persistence for canonical resources.

Maps to ``persistence.phi_repo`` in docs/DESIGN.md 1. Business logic goes through
this repository, never raw SQL/connections. Every write and read emits exactly
one audit event in the same transaction (docs/TEST_STRATEGY.md "Audit
completeness"), so an operation and its audit trail commit or roll back together.

RBAC field-level filtering and at-rest encryption attach here in later phases;
the shape (repository + mandatory audit) is in place now.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hip.messaging.canonical import model as m
from hip.messaging.canonical.mapper import CanonicalBundle
from hip.persistence.audit_log import AuditLog
from hip.persistence.models import PhiResource

# System actor used when ingestion writes on the pipeline's behalf (no end user).
SYSTEM_ACTOR = "system:ingestion"


class PhiRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditLog(session)

    async def _upsert(self, resource: m.CanonicalResource, *, actor: str) -> UUID:
        resource_type = type(resource).__name__
        payload = resource.model_dump(mode="json")
        stmt = pg_insert(PhiResource).values(
            canonical_id=resource.canonical_id,
            resource_type=resource_type,
            schema_version=resource.schema_version,
            payload=payload,
        )
        # Idempotent re-ingest: same canonical_id updates the stored document.
        stmt = stmt.on_conflict_do_update(
            index_elements=[PhiResource.canonical_id],
            set_={"payload": payload, "schema_version": resource.schema_version},
        )
        await self._session.execute(stmt)
        await self._audit.record(
            action="create",
            resource_type=resource_type,
            resource_id=resource.canonical_id,
            actor=actor,
        )
        return resource.canonical_id

    async def save_bundle(
        self, bundle: CanonicalBundle, *, actor: str = SYSTEM_ACTOR
    ) -> list[UUID]:
        """Persist every canonical entity in a mapped bundle. Returns their ids.

        The caller owns the transaction boundary (commit/rollback), so the whole
        bundle plus its audit entries are one atomic unit.
        """
        saved: list[UUID] = []
        resources: list[m.CanonicalResource] = []
        if bundle.patient is not None:
            resources.append(bundle.patient)
        if bundle.encounter is not None:
            resources.append(bundle.encounter)
        resources.extend(bundle.orders)
        resources.extend(bundle.observations)

        for resource in resources:
            saved.append(await self._upsert(resource, actor=actor))
        return saved

    async def get(self, canonical_id: UUID, *, actor: str) -> PhiResource | None:
        """Read one resource by id, emitting a read audit event."""
        result = await self._session.execute(
            select(PhiResource).where(PhiResource.canonical_id == canonical_id)
        )
        row = result.scalar_one_or_none()
        await self._audit.record(
            action="read",
            resource_type=row.resource_type if row else "unknown",
            resource_id=canonical_id,
            actor=actor,
        )
        return row
