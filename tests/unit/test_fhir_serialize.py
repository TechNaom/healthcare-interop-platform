"""Unit tests for canonical -> FHIR R4 serialization (Encounter, Observation)."""

from __future__ import annotations

from datetime import datetime

import pytest

from hip.messaging.canonical import model as m
from hip.messaging.canonical.fhir import to_fhir_encounter, to_fhir_observation

pytestmark = pytest.mark.unit


def test_encounter_serializes_with_required_fields() -> None:
    enc = m.Encounter(
        visit_number=m.Identifier(value="V100"),
        encounter_class=m.Coding(code="I"),
        status=m.EncounterStatus.in_progress,
        attending_provider=m.Reference(type="Practitioner", display="SMITH JOHN"),
        period=m.Period(start=datetime(2026, 8, 25, 10, 15)),
    )
    fhir = to_fhir_encounter(enc)
    assert fhir["resourceType"] == "Encounter"
    assert fhir["status"] == "in-progress"
    assert fhir["class"]["code"] == "I"
    assert fhir["identifier"][0]["value"] == "V100"
    assert fhir["participant"][0]["individual"]["display"] == "SMITH JOHN"
    start = fhir["period"]["start"]  # tz attached for FHIR dateTime (Z or +00:00)
    assert start.endswith("Z") or start.endswith("+00:00")


def test_encounter_defaults_required_fields_when_missing() -> None:
    fhir = to_fhir_encounter(m.Encounter())
    assert fhir["status"] == "unknown"
    assert fhir["class"]["code"] == "unknown"


@pytest.mark.parametrize(
    ("value", "expected_key"),
    [
        (m.Quantity(value=5.4, unit="mmol/L"), "valueQuantity"),
        ("within limits", "valueString"),
        (
            m.CodeableConcept(coding=[m.Coding(code="266927001", system="SCT")]),
            "valueCodeableConcept",
        ),
        (datetime(2026, 1, 1, 8, 0), "valueDateTime"),
        (True, "valueBoolean"),
    ],
)
def test_observation_polymorphic_value_maps_to_right_fhir_field(
    value: object, expected_key: str
) -> None:
    obs = m.Observation(
        observation_code=m.CodeableConcept(coding=[m.Coding(code="2339-0", system="LN")]),
        status=m.ObservationStatus.final,
        value=value,  # type: ignore[arg-type]
    )
    fhir = to_fhir_observation(obs)
    assert fhir["resourceType"] == "Observation"
    assert fhir["code"]["coding"][0]["code"] == "2339-0"
    assert expected_key in fhir


def test_observation_interpretation_and_reference_range() -> None:
    obs = m.Observation(
        observation_code=m.CodeableConcept(coding=[m.Coding(code="2339-0")]),
        status=m.ObservationStatus.final,
        value=m.Quantity(value=5.4, unit="mmol/L"),
        interpretation=["H"],
        reference_range="3.9-5.8",
        effective_time=datetime(2026, 8, 25, 9, 0),
    )
    fhir = to_fhir_observation(obs)
    assert fhir["interpretation"][0]["coding"][0]["code"] == "H"
    assert fhir["referenceRange"][0]["text"] == "3.9-5.8"
    eff = fhir["effectiveDateTime"]
    assert eff.endswith("Z") or eff.endswith("+00:00")


def test_observation_defaults_status_when_missing() -> None:
    obs = m.Observation(observation_code=m.CodeableConcept(coding=[m.Coding(code="x")]))
    assert to_fhir_observation(obs)["status"] == "unknown"
