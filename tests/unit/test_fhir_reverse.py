"""Unit tests for FHIR R4 -> canonical mapping (the write edge)."""

from __future__ import annotations

from datetime import date

import pytest

from hip.messaging.canonical import model as m
from hip.messaging.canonical.fhir import FhirParseError, from_fhir_patient, to_fhir_patient

pytestmark = pytest.mark.unit

_FHIR_PATIENT = {
    "resourceType": "Patient",
    "identifier": [{"system": "HOSP", "value": "MRN9", "type": {"coding": [{"code": "MR"}]}}],
    "name": [{"use": "official", "family": "SMITH", "given": ["ALICE"]}],
    "gender": "female",
    "birthDate": "1990-05-15",
    "address": [{"line": ["1 Elm St"], "city": "Town", "state": "CA", "postalCode": "90001"}],
    "telecom": [{"system": "phone", "value": "555-9999", "use": "home"}],
}


def test_maps_core_fields() -> None:
    p = from_fhir_patient(_FHIR_PATIENT)
    assert p.name[0].family == "SMITH"
    assert p.name[0].given == ["ALICE"]
    assert p.administrative_sex is m.AdministrativeGender.female
    assert p.birth_date == date(1990, 5, 15)
    assert p.identifiers[0].value == "MRN9"
    assert p.identifiers[0].type == "MR"
    assert p.address[0].city == "Town"
    assert p.telecom[0].value == "555-9999"


def test_fresh_id_assigned() -> None:
    a = from_fhir_patient(_FHIR_PATIENT)
    b = from_fhir_patient(_FHIR_PATIENT)
    assert a.canonical_id != b.canonical_id  # each create is a new instance


def test_round_trips_through_fhir() -> None:
    out = to_fhir_patient(from_fhir_patient(_FHIR_PATIENT))
    assert out["name"][0]["family"] == "SMITH"
    assert out["gender"] == "female"
    assert any(i["value"] == "MRN9" for i in out["identifier"])


def test_partial_birthdate_is_dropped_not_crashing() -> None:
    p = from_fhir_patient({"resourceType": "Patient", "birthDate": "1990"})
    assert p.birth_date is None  # partial FHIR date can't map to a full date


def test_invalid_fhir_raises() -> None:
    with pytest.raises(FhirParseError):
        from_fhir_patient({"resourceType": "Patient", "name": "not-a-list"})
