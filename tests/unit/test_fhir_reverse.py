"""Unit tests for FHIR R4 -> canonical mapping (the write edge)."""

from __future__ import annotations

from datetime import date

import pytest

from hip.messaging.canonical import model as m
from hip.messaging.canonical.fhir import (
    FhirParseError,
    from_fhir_encounter,
    from_fhir_observation,
    from_fhir_patient,
    to_fhir_patient,
)

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


def test_encounter_reverse_maps() -> None:
    enc = from_fhir_encounter(
        {
            "resourceType": "Encounter",
            "status": "in-progress",
            "class": {"code": "IMP", "system": "x"},
            "identifier": [{"value": "V9"}],
            "period": {"start": "2026-08-25T10:00:00Z"},
        }
    )
    assert enc.status is m.EncounterStatus.in_progress
    assert enc.encounter_class is not None and enc.encounter_class.code == "IMP"
    assert enc.visit_number is not None and enc.visit_number.value == "V9"
    assert enc.period is not None and enc.period.start is not None


def test_observation_reverse_maps_polymorphic_value() -> None:
    obs = from_fhir_observation(
        {
            "resourceType": "Observation",
            "status": "final",
            "code": {"coding": [{"code": "2339-0", "display": "Glucose"}]},
            "valueQuantity": {"value": 5.4, "unit": "mmol/L"},
            "interpretation": [{"coding": [{"code": "H"}]}],
            "referenceRange": [{"text": "3.9-5.8"}],
        }
    )
    assert obs.status is m.ObservationStatus.final
    assert obs.observation_code.coding[0].code == "2339-0"
    assert isinstance(obs.value, m.Quantity) and obs.value.value == 5.4
    assert obs.interpretation == ["H"]
    assert obs.reference_range == "3.9-5.8"


def test_observation_missing_required_fields_rejected() -> None:
    with pytest.raises(FhirParseError):
        from_fhir_observation({"resourceType": "Observation"})  # status + code are 1..1
