"""PHI repository — persistence for canonical resources, encrypted at rest.

Maps to ``persistence.phi_repo`` in docs/DESIGN.md 1. Business logic goes through
this repository, never raw SQL/connections. The canonical document is encrypted
by the injected ``KeyManager`` before storage and decrypted on read, so Postgres
only ever holds ciphertext (HIPAA 164.312(a)(2)(iv)). Every write and read emits
exactly one audit event in the same transaction (docs/TEST_STRATEGY.md "Audit
completeness").
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hip.messaging.canonical import model as m
from hip.messaging.canonical.mapper import CanonicalBundle
from hip.persistence.audit_log import AuditLog
from hip.persistence.models import PhiResource
from hip.security.keymanager import KeyManager

# System actor used when ingestion writes on the pipeline's behalf (no end user).
SYSTEM_ACTOR = "system:ingestion"


@dataclass(frozen=True, slots=True)
class StoredResource:
    """A decrypted view of a stored PHI resource."""

    canonical_id: UUID
    resource_type: str
    schema_version: str
    payload: dict[str, Any]


class PhiRepository:
    def __init__(self, session: AsyncSession, key_manager: KeyManager) -> None:
        self._session = session
        self._audit = AuditLog(session)
        self._keys = key_manager

    def _encrypt(self, payload: dict[str, Any]) -> bytes:
        return self._keys.encrypt(json.dumps(payload, separators=(",", ":")).encode())

    def _decrypt(self, ciphertext: bytes) -> dict[str, Any]:
        data: dict[str, Any] = json.loads(self._keys.decrypt(ciphertext))
        return data

    async def _upsert(self, resource: m.CanonicalResource, *, actor: str) -> UUID:
        resource_type = type(resource).__name__
        ciphertext = self._encrypt(resource.model_dump(mode="json"))
        stmt = pg_insert(PhiResource).values(
            canonical_id=resource.canonical_id,
            resource_type=resource_type,
            schema_version=resource.schema_version,
            payload_ciphertext=ciphertext,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[PhiResource.canonical_id],
            set_={
                "payload_ciphertext": ciphertext,
                "schema_version": resource.schema_version,
            },
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
        """Persist every canonical entity in a mapped bundle (encrypted). Returns ids."""
        resources: list[m.CanonicalResource] = []
        if bundle.patient is not None:
            resources.append(bundle.patient)
        if bundle.encounter is not None:
            resources.append(bundle.encounter)
        resources.extend(bundle.orders)
        resources.extend(bundle.observations)
        return [await self._upsert(r, actor=actor) for r in resources]

    async def get(self, canonical_id: UUID, *, actor: str) -> StoredResource | None:
        """Read + decrypt one resource by id, emitting a read audit event."""
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
        if row is None:
            return None
        return StoredResource(
            canonical_id=row.canonical_id,
            resource_type=row.resource_type,
            schema_version=row.schema_version,
            payload=self._decrypt(row.payload_ciphertext),
        )
