"""FHIR R4/R5 REST routes.

Maps to ``gateway.api.fhir`` in docs/DESIGN.md 1. Reads target the canonical
model (ADR-001) and render it as FHIR via ``canonical.fhir`` — routes never touch
HL7. Responses use ``application/fhir+json`` and a FHIR ``OperationOutcome`` on
error. Scope now: Patient/Encounter/Observation reads; write and search follow.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from hip.gateway.auth import Principal
from hip.gateway.deps import get_key_manager, get_session, require_role
from hip.gateway.min_necessary import FULL_ACCESS_ROLE, apply_minimum_necessary
from hip.messaging.canonical import fhir as serialize
from hip.messaging.canonical import model as m
from hip.persistence.phi_repo import PhiRepository, StoredResource
from hip.security.keymanager import KeyManager

router = APIRouter(prefix="/fhir", tags=["fhir"])

_FHIR_JSON = "application/fhir+json"

# RBAC role required to read clinical resources (SRS 5.1). ABAC/field-level
# filtering and SMART-on-FHIR scopes are refinements on top of this.
_READ_ROLE = "fhir:read"

# Shared dependency aliases keep the per-route signatures small.
SessionDep = Annotated[AsyncSession, Depends(get_session)]
PrincipalDep = Annotated[Principal, Depends(require_role(_READ_ROLE))]
KeyDep = Annotated[KeyManager, Depends(get_key_manager)]


def _operation_outcome(code: str, diagnostics: str, status_code: int) -> JSONResponse:
    body: dict[str, Any] = {
        "resourceType": "OperationOutcome",
        "issue": [{"severity": "error", "code": code, "diagnostics": diagnostics}],
    }
    return JSONResponse(body, status_code=status_code, media_type=_FHIR_JSON)


def _respond(resource_type: str, resource: dict[str, Any], principal: Principal) -> JSONResponse:
    """Apply minimum-necessary field filtering, then return FHIR JSON."""
    filtered = apply_minimum_necessary(
        resource_type, resource, full_access=principal.has_role(FULL_ACCESS_ROLE)
    )
    return JSONResponse(filtered, media_type=_FHIR_JSON)


async def _fetch(
    resource_type: str,
    canonical_id: UUID,
    session: AsyncSession,
    principal: Principal,
    key_manager: KeyManager,
) -> StoredResource | JSONResponse:
    """Read a stored resource of the expected type (emitting a read audit), or a
    404 OperationOutcome."""
    stored = await PhiRepository(session, key_manager).get(canonical_id, actor=principal.subject)
    await session.commit()
    if stored is None or stored.resource_type != resource_type:
        return _operation_outcome("not-found", f"{resource_type}/{canonical_id} not found", 404)
    return stored


@router.get("/Patient/{canonical_id}")
async def read_patient(
    canonical_id: UUID, session: SessionDep, principal: PrincipalDep, key_manager: KeyDep
) -> JSONResponse:
    """Return a stored patient as a FHIR R4 Patient (or a 404 OperationOutcome)."""
    result = await _fetch("Patient", canonical_id, session, principal, key_manager)
    if isinstance(result, JSONResponse):
        return result
    return _respond(
        "Patient", serialize.to_fhir_patient(m.Patient.model_validate(result.payload)), principal
    )


@router.get("/Encounter/{canonical_id}")
async def read_encounter(
    canonical_id: UUID, session: SessionDep, principal: PrincipalDep, key_manager: KeyDep
) -> JSONResponse:
    """Return a stored encounter as a FHIR R4 Encounter (or a 404 OperationOutcome)."""
    result = await _fetch("Encounter", canonical_id, session, principal, key_manager)
    if isinstance(result, JSONResponse):
        return result
    return _respond(
        "Encounter",
        serialize.to_fhir_encounter(m.Encounter.model_validate(result.payload)),
        principal,
    )


@router.get("/Observation/{canonical_id}")
async def read_observation(
    canonical_id: UUID, session: SessionDep, principal: PrincipalDep, key_manager: KeyDep
) -> JSONResponse:
    """Return a stored observation as a FHIR R4 Observation (or a 404 OperationOutcome)."""
    result = await _fetch("Observation", canonical_id, session, principal, key_manager)
    if isinstance(result, JSONResponse):
        return result
    return _respond(
        "Observation",
        serialize.to_fhir_observation(m.Observation.model_validate(result.payload)),
        principal,
    )
