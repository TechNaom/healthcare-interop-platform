"""FHIR R4/R5 REST routes.

Maps to ``gateway.api.fhir`` in docs/DESIGN.md 1. Reads target the canonical
model (ADR-001) and render it as FHIR via ``canonical.fhir`` — routes never touch
HL7. Responses use ``application/fhir+json`` and a FHIR ``OperationOutcome`` on
error. Scope now: Patient/Encounter/Observation/ServiceRequest read + write, and
identifier search for Patient/Encounter/Observation via the blind index.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from hip.gateway.auth import Principal
from hip.gateway.deps import (
    get_blind_indexer,
    get_key_manager,
    get_optional_blind_indexer,
    get_session,
    require_role,
)
from hip.gateway.min_necessary import FULL_ACCESS_ROLE, apply_minimum_necessary
from hip.messaging.canonical import fhir as serialize
from hip.messaging.canonical import model as m
from hip.messaging.canonical.fhir import FhirParseError
from hip.persistence.phi_repo import PhiRepository, StoredResource
from hip.security.blind_index import BlindIndexer
from hip.security.keymanager import KeyManager

router = APIRouter(prefix="/fhir", tags=["fhir"])

_FHIR_JSON = "application/fhir+json"

# Per-resource serializer: parse the stored payload into its canonical model and
# render it as FHIR. Used by the shared identifier-search helper so each search
# route is a one-liner (the read routes call the typed serializers directly).
_SERIALIZERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "Patient": lambda p: serialize.to_fhir_patient(m.Patient.model_validate(p)),
    "Encounter": lambda p: serialize.to_fhir_encounter(m.Encounter.model_validate(p)),
    "Observation": lambda p: serialize.to_fhir_observation(m.Observation.model_validate(p)),
}

# RBAC roles (SRS 5.1). read = view resources; write = create/update.
_READ_ROLE = "fhir:read"
_WRITE_ROLE = "fhir:write"

# Shared dependency aliases keep the per-route signatures small.
SessionDep = Annotated[AsyncSession, Depends(get_session)]
PrincipalDep = Annotated[Principal, Depends(require_role(_READ_ROLE))]
WritePrincipalDep = Annotated[Principal, Depends(require_role(_WRITE_ROLE))]
KeyDep = Annotated[KeyManager, Depends(get_key_manager)]
BlindDep = Annotated[BlindIndexer, Depends(get_blind_indexer)]
OptBlindDep = Annotated[BlindIndexer | None, Depends(get_optional_blind_indexer)]


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


async def _fetch(  # noqa: PLR0913 - cohesive read helper shared by all read routes
    resource_type: str,
    canonical_id: UUID,
    session: AsyncSession,
    principal: Principal,
    key_manager: KeyManager,
    *,
    display_type: str | None = None,
) -> StoredResource | JSONResponse:
    """Read a stored resource of the expected canonical type (emitting a read
    audit), or a 404 OperationOutcome. ``display_type`` overrides the type name in
    the 404 message when the FHIR name differs from the stored one (Order↔ServiceRequest)."""
    stored = await PhiRepository(session, key_manager).get(canonical_id, actor=principal.subject)
    await session.commit()
    if stored is None or stored.resource_type != resource_type:
        shown = display_type or resource_type
        return _operation_outcome("not-found", f"{shown}/{canonical_id} not found", 404)
    return stored


async def _search_by_identifier(  # noqa: PLR0913, PLR0917 - cohesive search helper shared by all search routes
    resource_type: str,
    identifier: str,
    session: AsyncSession,
    principal: Principal,
    key_manager: KeyManager,
    blind_indexer: BlindIndexer,
) -> JSONResponse:
    """Search ``resource_type`` by identifier via the blind index → FHIR Bundle.

    ``identifier`` may be ``system|value`` or a bare ``value``; the value is
    matched exactly against the HMAC index (no plaintext hits the query). Each
    entry is minimum-necessary filtered for the caller and read-audited.
    """
    value = identifier.rsplit("|", 1)[-1]
    serialize_payload = _SERIALIZERS[resource_type]
    repo = PhiRepository(session, key_manager, blind_indexer)
    ids = await repo.find_ids_by_identifier(resource_type, value)

    full = principal.has_role(FULL_ACCESS_ROLE)
    entries: list[dict[str, Any]] = []
    for canonical_id in ids:
        stored = await repo.get(canonical_id, actor=principal.subject)
        if stored is None:
            continue
        resource = serialize_payload(stored.payload)
        entries.append(
            {"resource": apply_minimum_necessary(resource_type, resource, full_access=full)}
        )
    await session.commit()

    bundle: dict[str, Any] = {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(entries),
        "entry": entries,
    }
    return JSONResponse(bundle, media_type=_FHIR_JSON)


@router.get("/Patient")
async def search_patient(
    session: SessionDep,
    principal: PrincipalDep,
    key_manager: KeyDep,
    blind_indexer: BlindDep,
    identifier: str,
) -> JSONResponse:
    """Search patients by identifier via the blind index. Returns a FHIR Bundle."""
    return await _search_by_identifier(
        "Patient", identifier, session, principal, key_manager, blind_indexer
    )


@router.get("/Encounter")
async def search_encounter(
    session: SessionDep,
    principal: PrincipalDep,
    key_manager: KeyDep,
    blind_indexer: BlindDep,
    identifier: str,
) -> JSONResponse:
    """Search encounters by identifier (visit or account number) via the blind index."""
    return await _search_by_identifier(
        "Encounter", identifier, session, principal, key_manager, blind_indexer
    )


@router.get("/Observation")
async def search_observation(
    session: SessionDep,
    principal: PrincipalDep,
    key_manager: KeyDep,
    blind_indexer: BlindDep,
    identifier: str,
) -> JSONResponse:
    """Search observations by identifier via the blind index."""
    return await _search_by_identifier(
        "Observation", identifier, session, principal, key_manager, blind_indexer
    )


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


async def _persist_created(  # noqa: PLR0913, PLR0917 - cohesive create helper for 4 routes
    resource: m.CanonicalResource,
    resource_type: str,
    fhir_body: dict[str, Any],
    session: AsyncSession,
    principal: Principal,
    key_manager: KeyManager,
    blind_indexer: BlindIndexer | None,
) -> JSONResponse:
    """Persist a newly-mapped resource (encrypted + audited) and return 201."""
    await PhiRepository(session, key_manager, blind_indexer).save(resource, actor=principal.subject)
    await session.commit()
    location = f"/fhir/{resource_type}/{resource.canonical_id}"
    return JSONResponse(
        fhir_body, status_code=201, media_type=_FHIR_JSON, headers={"Location": location}
    )


@router.post("/Patient", status_code=201)
async def create_patient(
    session: SessionDep,
    principal: WritePrincipalDep,
    key_manager: KeyDep,
    blind_indexer: OptBlindDep,
    body: Annotated[dict[str, Any], Body(media_type=_FHIR_JSON)],
) -> JSONResponse:
    """Create a Patient from a FHIR R4 body. 201 + Location, or 400 on invalid FHIR."""
    try:
        patient = serialize.from_fhir_patient(body)
    except FhirParseError as exc:
        return _operation_outcome("invalid", f"invalid FHIR Patient: {exc}", 400)
    created = serialize.to_fhir_patient(patient)
    return await _persist_created(
        patient, "Patient", created, session, principal, key_manager, blind_indexer
    )


@router.post("/Encounter", status_code=201)
async def create_encounter(
    session: SessionDep,
    principal: WritePrincipalDep,
    key_manager: KeyDep,
    blind_indexer: OptBlindDep,
    body: Annotated[dict[str, Any], Body(media_type=_FHIR_JSON)],
) -> JSONResponse:
    """Create an Encounter from a FHIR R4 body. 201 + Location, or 400 on invalid FHIR."""
    try:
        encounter = serialize.from_fhir_encounter(body)
    except FhirParseError as exc:
        return _operation_outcome("invalid", f"invalid FHIR Encounter: {exc}", 400)
    created = serialize.to_fhir_encounter(encounter)
    return await _persist_created(
        encounter, "Encounter", created, session, principal, key_manager, blind_indexer
    )


@router.post("/Observation", status_code=201)
async def create_observation(
    session: SessionDep,
    principal: WritePrincipalDep,
    key_manager: KeyDep,
    blind_indexer: OptBlindDep,
    body: Annotated[dict[str, Any], Body(media_type=_FHIR_JSON)],
) -> JSONResponse:
    """Create an Observation from a FHIR R4 body. 201 + Location, or 400 on invalid FHIR."""
    try:
        observation = serialize.from_fhir_observation(body)
    except FhirParseError as exc:
        return _operation_outcome("invalid", f"invalid FHIR Observation: {exc}", 400)
    created = serialize.to_fhir_observation(observation)
    return await _persist_created(
        observation, "Observation", created, session, principal, key_manager, blind_indexer
    )


@router.get("/ServiceRequest/{canonical_id}")
async def read_service_request(
    canonical_id: UUID, session: SessionDep, principal: PrincipalDep, key_manager: KeyDep
) -> JSONResponse:
    """Return a stored order as a FHIR R4 ServiceRequest (or a 404 OperationOutcome)."""
    # Canonical resource type is "Order"; the FHIR name is ServiceRequest.
    result = await _fetch(
        "Order", canonical_id, session, principal, key_manager, display_type="ServiceRequest"
    )
    if isinstance(result, JSONResponse):
        return result
    return _respond(
        "ServiceRequest",
        serialize.to_fhir_service_request(m.Order.model_validate(result.payload)),
        principal,
    )


@router.post("/ServiceRequest", status_code=201)
async def create_service_request(
    session: SessionDep,
    principal: WritePrincipalDep,
    key_manager: KeyDep,
    blind_indexer: OptBlindDep,
    body: Annotated[dict[str, Any], Body(media_type=_FHIR_JSON)],
) -> JSONResponse:
    """Create an Order from a FHIR R4 ServiceRequest. 201 + Location, or 400 on invalid."""
    try:
        order = serialize.from_fhir_service_request(body)
    except FhirParseError as exc:
        return _operation_outcome("invalid", f"invalid FHIR ServiceRequest: {exc}", 400)
    created = serialize.to_fhir_service_request(order)
    return await _persist_created(
        order, "ServiceRequest", created, session, principal, key_manager, blind_indexer
    )
