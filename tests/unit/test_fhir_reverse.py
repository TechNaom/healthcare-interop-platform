"""Unit tests for FHIR R4 -> canonical mapping (the write edge)."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from hip.messaging.canonical import model as m
from hip.messaging.canonical.fhir import (
    FhirParseError,
    from_fhir_diagnostic_report,
    from_fhir_encounter,
    from_fhir_observation,
    from_fhir_patient,
    from_fhir_service_request,
    to_fhir_diagnostic_report,
    to_fhir_observation,
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


def test_observation_identifier_round_trips() -> None:
    """Identifier must survive FHIR->canonical->FHIR so it can be blind-indexed for search."""
    obs = from_fhir_observation(
        {
            "resourceType": "Observation",
            "status": "final",
            "code": {"coding": [{"code": "2339-0"}]},
            "identifier": [{"system": "LAB", "value": "OBS-77"}],
        }
    )
    assert [i.value for i in obs.identifiers] == ["OBS-77"]
    rendered = to_fhir_observation(obs)
    assert any(i["value"] == "OBS-77" for i in rendered["identifier"])


def test_service_request_reverse_maps() -> None:
    order = from_fhir_service_request(
        {
            "resourceType": "ServiceRequest",
            "status": "active",
            "intent": "order",
            "subject": {"display": "x"},
            "code": {"coding": [{"code": "2339-0"}]},
            "identifier": [
                {"value": "P1", "type": {"coding": [{"code": "PLAC"}]}},
                {"value": "F1", "type": {"coding": [{"code": "FILL"}]}},
            ],
        }
    )
    assert order.status is m.RequestStatus.active
    assert order.intent is m.RequestIntent.order
    assert order.ordered_item is not None and order.ordered_item.coding[0].code == "2339-0"
    assert order.placer_order_number is not None and order.placer_order_number.value == "P1"
    assert order.filler_order_number is not None and order.filler_order_number.value == "F1"


def test_service_request_missing_required_rejected() -> None:
    with pytest.raises(FhirParseError):
        from_fhir_service_request({"resourceType": "ServiceRequest", "status": "active"})


def test_diagnostic_report_reverse_maps_and_round_trips() -> None:
    obs_id = uuid4()
    report = from_fhir_diagnostic_report(
        {
            "resourceType": "DiagnosticReport",
            "status": "final",
            "code": {"coding": [{"code": "58410-2", "display": "CBC panel"}]},
            "identifier": [{"value": "FILL-1"}],
            "effectiveDateTime": "2026-01-02T03:04:00Z",
            "result": [{"reference": f"Observation/{obs_id}"}],
        }
    )
    assert report.status is m.DiagnosticReportStatus.final
    assert report.code.coding[0].code == "58410-2"
    assert [i.value for i in report.identifiers] == ["FILL-1"]
    assert report.results[0].type == "Observation"
    assert report.results[0].canonical_id == obs_id

    rendered = to_fhir_diagnostic_report(report)
    assert rendered["status"] == "final"
    assert rendered["result"][0]["reference"] == f"Observation/{obs_id}"


def test_diagnostic_report_missing_required_rejected() -> None:
    with pytest.raises(FhirParseError):
        from_fhir_diagnostic_report({"resourceType": "DiagnosticReport", "status": "final"})
