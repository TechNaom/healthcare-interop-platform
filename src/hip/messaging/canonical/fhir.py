"""Canonical -> FHIR R4 serialization (the FHIR edge of ADR-001).

The counterpart to ``mapper`` (HL7 -> canonical): here the canonical model is
rendered as FHIR R4 resources. Everything is built as a FHIR-JSON dict and then
validated through ``fhir.resources`` (R4B) so the output is guaranteed
well-formed R4 — invalid vocab or shapes fail here, not at the client.

Scope now: Patient. Encounter/Observation/ServiceRequest follow the same pattern
and land as the read API grows.
"""

from __future__ import annotations

from typing import Any

from fhir.resources.R4B.patient import Patient as FHIRPatient

from hip.messaging.canonical import model as m

_V2_0203 = "http://terminology.hl7.org/CodeSystem/v2-0203"  # identifier type codes

# Canonical NameUse -> FHIR name-use codes (FHIR has no "legal").
_NAME_USE = {
    m.NameUse.legal: "official",
    m.NameUse.official: "official",
    m.NameUse.usual: "usual",
    m.NameUse.maiden: "maiden",
    m.NameUse.alias: "nickname",
}


def _identifier(identifier: m.Identifier) -> dict[str, Any]:
    out: dict[str, Any] = {"value": identifier.value}
    if identifier.system:
        out["system"] = identifier.system
    if identifier.type:
        out["type"] = {"coding": [{"system": _V2_0203, "code": identifier.type}]}
    return out


def _name(name: m.HumanName) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if name.family:
        out["family"] = name.family
    if name.given:
        out["given"] = name.given
    if name.prefix:
        out["prefix"] = name.prefix
    if name.suffix:
        out["suffix"] = name.suffix
    if name.use and name.use in _NAME_USE:
        out["use"] = _NAME_USE[name.use]
    return out


def _address(address: m.Address) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if address.lines:
        out["line"] = address.lines
    for canonical_field, fhir_field in (
        ("city", "city"),
        ("state", "state"),
        ("postal_code", "postalCode"),
        ("country", "country"),
    ):
        value = getattr(address, canonical_field)
        if value:
            out[fhir_field] = value
    if address.use:
        out["use"] = address.use.value
    return out


def _telecom(contact: m.ContactPoint) -> dict[str, Any]:
    out: dict[str, Any] = {"value": contact.value}
    if contact.system:
        out["system"] = contact.system.value
    if contact.use:
        out["use"] = contact.use.value
    return out


def to_fhir_patient(patient: m.Patient) -> dict[str, Any]:
    """Render a canonical Patient as a validated FHIR R4 Patient JSON dict."""
    identifiers = [_identifier(i) for i in patient.identifiers]
    if patient.account_number is not None:
        identifiers.append(_identifier(patient.account_number))

    data: dict[str, Any] = {
        "resourceType": "Patient",
        "id": str(patient.canonical_id),
    }
    if identifiers:
        data["identifier"] = identifiers
    names = [n for n in (_name(name) for name in patient.name) if n]
    if names:
        data["name"] = names
    if patient.administrative_sex is not None:
        data["gender"] = patient.administrative_sex.value
    if patient.birth_date is not None:
        data["birthDate"] = patient.birth_date.isoformat()
    addresses = [a for a in (_address(addr) for addr in patient.address) if a]
    if addresses:
        data["address"] = addresses
    telecom = [_telecom(c) for c in patient.telecom]
    if telecom:
        data["telecom"] = telecom
    if patient.deceased_datetime is not None:
        data["deceasedDateTime"] = patient.deceased_datetime.isoformat()
    elif patient.deceased is not None:
        data["deceasedBoolean"] = patient.deceased

    # Validate through fhir.resources so malformed output fails here, not downstream.
    return FHIRPatient.model_validate(data).model_dump(mode="json", exclude_none=True)
