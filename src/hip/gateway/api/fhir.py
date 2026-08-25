"""FHIR R4/R5 REST routes.

Maps to ``gateway.api.fhir`` in docs/DESIGN.md 1. Reads target the canonical
model (ADR-001) and render it as FHIR via ``canonical.fhir`` — routes never touch
HL7. Responses use ``application/fhir+json`` and a FHIR ``OperationOutcome`` on
error. Scope now: Patient read; other resources and search follow.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from hip.gateway.deps import get_session
from hip.messaging.canonical import model as m
from hip.messaging.canonical.fhir import to_fhir_patient
from hip.persistence.phi_repo import PhiRepository

router = APIRouter(prefix="/fhir", tags=["fhir"])

_FHIR_JSON = "application/fhir+json"


def _operation_outcome(code: str, diagnostics: str, status_code: int) -> JSONResponse:
    body: dict[str, Any] = {
        "resourceType": "OperationOutcome",
        "issue": [{"severity": "error", "code": code, "diagnostics": diagnostics}],
    }
    return JSONResponse(body, status_code=status_code, media_type=_FHIR_JSON)


@router.get("/Patient/{canonical_id}")
async def read_patient(
    canonical_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JSONResponse:
    """Return a stored patient as a FHIR R4 Patient (or a 404 OperationOutcome)."""
    repo = PhiRepository(session)
    row = await repo.get(canonical_id, actor="api:read")  # emits a read audit
    await session.commit()

    if row is None or row.resource_type != "Patient":
        return _operation_outcome("not-found", f"Patient/{canonical_id} not found", 404)

    patient = m.Patient.model_validate(row.payload)
    return JSONResponse(to_fhir_patient(patient), media_type=_FHIR_JSON)
