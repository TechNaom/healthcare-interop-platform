"""Canonical -> FHIR R4 serialization (the FHIR edge of ADR-001).

The counterpart to ``mapper`` (HL7 -> canonical): here the canonical model is
rendered as FHIR R4 resources. Everything is built as a FHIR-JSON dict and then
validated through ``fhir.resources`` (R4B) so the output is guaranteed
well-formed R4 — invalid vocab or shapes fail here, not at the client.

Scope now: Patient. Encounter/Observation/ServiceRequest follow the same pattern
and land as the read API grows.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from fhir.resources.R4B.encounter import Encounter as FHIREncounter
from fhir.resources.R4B.observation import Observation as FHIRObservation
from fhir.resources.R4B.patient import Patient as FHIRPatient
from pydantic import ValidationError

from hip.messaging.canonical import model as m

_V2_0203 = "http://terminology.hl7.org/CodeSystem/v2-0203"  # identifier type codes
_V3_INTERPRETATION = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"

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


def _fhir_datetime(value: datetime) -> str:
    """FHIR ``dateTime`` requires a timezone when a time is present. HL7 offsets
    are dropped on ingest, so a naive value is treated as UTC here."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _coding(coding: m.Coding) -> dict[str, Any]:
    out: dict[str, Any] = {"code": coding.code}
    if coding.system:
        out["system"] = coding.system
    if coding.display:
        out["display"] = coding.display
    return out


def _codeable_concept(concept: m.CodeableConcept) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if concept.coding:
        out["coding"] = [_coding(c) for c in concept.coding]
    if concept.text:
        out["text"] = concept.text
    return out


def _reference(reference: m.Reference) -> dict[str, Any]:
    """FHIR Reference: prefer a resolvable ``Type/id``, else fall back to display."""
    out: dict[str, Any] = {}
    if reference.canonical_id is not None:
        out["reference"] = f"{reference.type}/{reference.canonical_id}"
    if reference.display:
        out["display"] = reference.display
    return out


def _period(period: m.Period) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if period.start is not None:
        out["start"] = _fhir_datetime(period.start)
    if period.end is not None:
        out["end"] = _fhir_datetime(period.end)
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
        data["deceasedDateTime"] = _fhir_datetime(patient.deceased_datetime)
    elif patient.deceased is not None:
        data["deceasedBoolean"] = patient.deceased

    # Validate through fhir.resources so malformed output fails here, not downstream.
    return FHIRPatient.model_validate(data).model_dump(mode="json", exclude_none=True)


def to_fhir_encounter(encounter: m.Encounter) -> dict[str, Any]:
    """Render a canonical Encounter as a validated FHIR R4 Encounter JSON dict."""
    identifiers = [
        _identifier(i) for i in (encounter.visit_number, encounter.account_number) if i is not None
    ]

    data: dict[str, Any] = {
        "resourceType": "Encounter",
        "id": str(encounter.canonical_id),
        # status is 1..1 in R4; "unknown" is the valid stand-in when unset.
        "status": encounter.status.value if encounter.status else "unknown",
        # class is 1..1 in R4 — carry the mapped code, or "unknown".
        "class": _coding(encounter.encounter_class)
        if encounter.encounter_class
        else {"code": "unknown"},
    }
    if identifiers:
        data["identifier"] = identifiers
    if encounter.patient_ref is not None:
        data["subject"] = _reference(encounter.patient_ref)
    participants = []
    for provider, type_code in (
        (encounter.attending_provider, "ATND"),
        (encounter.referring_provider, "REF"),
    ):
        if provider is not None:
            participants.append(
                {"type": [{"coding": [{"code": type_code}]}], "individual": _reference(provider)}
            )
    if participants:
        data["participant"] = participants
    if encounter.period is not None and (encounter.period.start or encounter.period.end):
        data["period"] = _period(encounter.period)

    return FHIREncounter.model_validate(data).model_dump(mode="json", exclude_none=True)


def _observation_value(value: m.ObservationValue) -> dict[str, Any]:
    """Render a polymorphic OBX-5 value as the right FHIR value[x] field."""
    if isinstance(value, m.Quantity):
        quantity: dict[str, Any] = {"value": value.value}
        if value.unit:
            quantity["unit"] = value.unit
        if value.comparator:
            quantity["comparator"] = value.comparator
        return {"valueQuantity": quantity}
    if isinstance(value, m.CodeableConcept):
        return {"valueCodeableConcept": _codeable_concept(value)}
    if isinstance(value, bool):  # before int — bool is a subclass of int
        return {"valueBoolean": value}
    if isinstance(value, datetime):
        return {"valueDateTime": _fhir_datetime(value)}
    if isinstance(value, int | float):
        return {"valueQuantity": {"value": float(value)}}
    return {"valueString": str(value)}


def to_fhir_observation(observation: m.Observation) -> dict[str, Any]:
    """Render a canonical Observation as a validated FHIR R4 Observation JSON dict."""
    data: dict[str, Any] = {
        "resourceType": "Observation",
        "id": str(observation.canonical_id),
        # status and code are both 1..1 in R4.
        "status": observation.status.value if observation.status else "unknown",
        "code": _codeable_concept(observation.observation_code),
    }
    if observation.value is not None:
        data.update(_observation_value(observation.value))
    if observation.patient_ref is not None:
        data["subject"] = _reference(observation.patient_ref)
    if observation.encounter_ref is not None:
        data["encounter"] = _reference(observation.encounter_ref)
    if observation.effective_time is not None:
        data["effectiveDateTime"] = _fhir_datetime(observation.effective_time)
    if observation.interpretation:
        data["interpretation"] = [
            {"coding": [{"system": _V3_INTERPRETATION, "code": flag}]}
            for flag in observation.interpretation
        ]
    if observation.reference_range:
        data["referenceRange"] = [{"text": observation.reference_range}]

    return FHIRObservation.model_validate(data).model_dump(mode="json", exclude_none=True)


# --------------------------------------------------------------------------- #
# FHIR -> canonical (the write edge). Validate the incoming FHIR, then map from
# the plain JSON so we don't wrestle with library value-types.
# --------------------------------------------------------------------------- #
class FhirParseError(Exception):
    """Raised when an incoming FHIR resource is invalid or unmappable."""


# FHIR name-use -> canonical NameUse (reverse of _NAME_USE).
_NAME_USE_REVERSE = {
    "official": m.NameUse.official,
    "usual": m.NameUse.usual,
    "nickname": m.NameUse.alias,
    "maiden": m.NameUse.maiden,
}


def _enum_or_none[E: StrEnum](enum_cls: type[E], value: Any) -> E | None:
    try:
        return enum_cls(value)
    except ValueError:
        return None


def _identifier_in(data: dict[str, Any]) -> m.Identifier | None:
    value = data.get("value")
    if not value:
        return None
    type_code = None
    coding = (data.get("type") or {}).get("coding") or []
    if coding:
        type_code = coding[0].get("code")
    return m.Identifier(value=value, system=data.get("system"), type=type_code)


def _name_in(data: dict[str, Any]) -> m.HumanName:
    return m.HumanName(
        family=data.get("family"),
        given=list(data.get("given", [])),
        prefix=list(data.get("prefix", [])),
        suffix=list(data.get("suffix", [])),
        use=_NAME_USE_REVERSE.get(data.get("use", "")),
    )


def _address_in(data: dict[str, Any]) -> m.Address:
    return m.Address(
        lines=list(data.get("line", [])),
        city=data.get("city"),
        state=data.get("state"),
        postal_code=data.get("postalCode"),
        country=data.get("country"),
        use=_enum_or_none(m.AddressUse, data.get("use")),
    )


def _date_in(value: Any) -> date | None:
    """FHIR date may be partial (YYYY / YYYY-MM); keep only full YYYY-MM-DD."""
    try:
        return date.fromisoformat(value) if value else None
    except (ValueError, TypeError):
        return None


def _datetime_in(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except (ValueError, TypeError):
        return None


def _telecom_in(data: dict[str, Any]) -> m.ContactPoint | None:
    value = data.get("value")
    if not value:
        return None
    return m.ContactPoint(
        system=_enum_or_none(m.ContactPointSystem, data.get("system")),
        value=value,
        use=_enum_or_none(m.ContactPointUse, data.get("use")),
    )


def from_fhir_patient(data: dict[str, Any]) -> m.Patient:
    """Map an incoming FHIR R4 Patient to a new canonical Patient (fresh id).

    Raises ``FhirParseError`` if the payload isn't valid FHIR R4 Patient.
    """
    try:
        FHIRPatient.model_validate(data)  # structural validation only
    except ValidationError as exc:
        raise FhirParseError(str(exc)) from exc

    return m.Patient(
        identifiers=[i for i in (_identifier_in(d) for d in data.get("identifier", [])) if i],
        name=[_name_in(d) for d in data.get("name", [])],
        birth_date=_date_in(data.get("birthDate")),
        administrative_sex=_enum_or_none(m.AdministrativeGender, data.get("gender")),
        address=[_address_in(d) for d in data.get("address", [])],
        telecom=[t for t in (_telecom_in(d) for d in data.get("telecom", [])) if t],
        deceased=data.get("deceasedBoolean"),
        deceased_datetime=_datetime_in(data.get("deceasedDateTime")),
    )


def _coding_in(data: dict[str, Any]) -> m.Coding:
    return m.Coding(
        code=data.get("code", ""), system=data.get("system"), display=data.get("display")
    )


def _codeable_concept_in(data: dict[str, Any]) -> m.CodeableConcept:
    return m.CodeableConcept(
        coding=[_coding_in(c) for c in data.get("coding", []) if c.get("code")],
        text=data.get("text"),
    )


def _period_in(data: dict[str, Any] | None) -> m.Period | None:
    if not data:
        return None
    return m.Period(start=_datetime_in(data.get("start")), end=_datetime_in(data.get("end")))


def from_fhir_encounter(data: dict[str, Any]) -> m.Encounter:
    """Map an incoming FHIR R4 Encounter to a new canonical Encounter (fresh id)."""
    try:
        FHIREncounter.model_validate(data)
    except ValidationError as exc:
        raise FhirParseError(str(exc)) from exc

    identifiers = data.get("identifier", [])
    fhir_class = data.get("class")
    return m.Encounter(
        status=_enum_or_none(m.EncounterStatus, data.get("status")),
        encounter_class=_coding_in(fhir_class) if fhir_class and fhir_class.get("code") else None,
        visit_number=_identifier_in(identifiers[0]) if identifiers else None,
        period=_period_in(data.get("period")),
    )


def _observation_value_in(data: dict[str, Any]) -> m.ObservationValue | None:
    """Read the FHIR value[x] field back into a canonical polymorphic value."""
    if "valueQuantity" in data:
        quantity = data["valueQuantity"]
        return m.Quantity(
            value=float(quantity["value"]),
            unit=quantity.get("unit"),
            comparator=quantity.get("comparator"),
        )
    if "valueCodeableConcept" in data:
        return _codeable_concept_in(data["valueCodeableConcept"])
    if "valueDateTime" in data:
        return _datetime_in(data["valueDateTime"])
    if "valueBoolean" in data:
        return bool(data["valueBoolean"])
    if "valueString" in data:
        return str(data["valueString"])
    return None


def from_fhir_observation(data: dict[str, Any]) -> m.Observation:
    """Map an incoming FHIR R4 Observation to a new canonical Observation (fresh id)."""
    try:
        FHIRObservation.model_validate(data)
    except ValidationError as exc:
        raise FhirParseError(str(exc)) from exc

    ranges = data.get("referenceRange") or []
    return m.Observation(
        observation_code=_codeable_concept_in(data.get("code", {})),
        status=_enum_or_none(m.ObservationStatus, data.get("status")),
        value=_observation_value_in(data),
        effective_time=_datetime_in(data.get("effectiveDateTime")),
        interpretation=[
            coding["code"]
            for interp in data.get("interpretation", [])
            for coding in interp.get("coding", [])
            if coding.get("code")
        ],
        reference_range=ranges[0].get("text") if ranges else None,
    )
