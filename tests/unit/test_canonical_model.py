"""Unit tests for the canonical model (docs/DATA_MODEL.md v0.2.0, ADR-001).

Structure/behaviour of the types, not mapping logic (the mapper is still a stub).
These lock the properties the model *guarantees* to every layer that depends on
it: stable identity, schema versioning, strictness, and polymorphic values.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from hip.messaging.canonical import model as m

pytestmark = pytest.mark.unit


def test_resource_gets_unique_id_and_schema_version() -> None:
    a = m.Patient()
    b = m.Patient()
    assert isinstance(a.canonical_id, UUID)
    assert a.canonical_id != b.canonical_id  # identity is per-instance
    assert a.schema_version == m.CANONICAL_SCHEMA_VERSION


def test_extra_fields_are_rejected() -> None:
    """extra='forbid' makes a mapping typo fail loudly rather than silently drop."""
    with pytest.raises(ValidationError):
        m.Patient(birthDate="1980-01-01")  # type: ignore[call-arg]  # camelCase typo


def test_patient_carries_both_identifiers_and_account_number() -> None:
    p = m.Patient(
        identifiers=[m.Identifier(system="MRN", value="12345")],
        account_number=m.Identifier(value="A99", type="AN"),
        name=[m.HumanName(family="Doe", given=["Jane"], use=m.NameUse.legal)],
        birth_date=date(1980, 1, 1),
        administrative_sex=m.AdministrativeGender.female,
    )
    assert p.identifiers[0].value == "12345"
    assert p.account_number is not None and p.account_number.type == "AN"


def test_encounter_identity_source_is_configurable_not_hardcoded() -> None:
    """Both visit_number (PV1-19) and account_number (PID-18) are retained; which
    is authoritative is per-source config (docs/DATA_MODEL.md 'Encounter identity')."""
    enc = m.Encounter(
        visit_number=m.Identifier(value="V1"),
        account_number=m.Identifier(value="A1", type="AN"),
        identity_source=m.IdentitySource.account_number,
        status=m.EncounterStatus.in_progress,
    )
    assert enc.visit_number and enc.account_number
    assert enc.identity_source is m.IdentitySource.account_number
    assert enc.status is not None
    assert enc.status.value == "in-progress"  # hyphenated FHIR code preserved


def test_order_defaults_to_order_intent() -> None:
    o = m.Order(placer_order_number=m.Identifier(value="P1", type="PLAC"))
    assert o.intent is m.RequestIntent.order


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        (m.Quantity(value=5.4, unit="mmol/L"), m.Quantity),
        ("positive", str),
        (m.CodeableConcept(text="detected"), m.CodeableConcept),
        (datetime(2026, 1, 1, 12, 0), datetime),
        (True, bool),
    ],
)
def test_observation_value_is_polymorphic(value: object, kind: type) -> None:
    """OBX-5 value is selected by OBX-2 type — not always a Quantity."""
    obs = m.Observation(
        observation_code=m.CodeableConcept(coding=[m.Coding(system="LOINC", code="2339-0")]),
        value=value,  # type: ignore[arg-type]
        status=m.ObservationStatus.final,
    )
    assert isinstance(obs.value, kind)


def test_observation_requires_a_code() -> None:
    """observation_code (OBX-3) is the central field and is required."""
    with pytest.raises(ValidationError):
        m.Observation()  # type: ignore[call-arg]


def test_dead_letter_is_modelled_and_round_trips() -> None:
    dlm = m.DeadLetterMessage(
        received_at=datetime(2026, 8, 24, 10, 0),
        raw_message="MSH|^~\\&|...",
        failure_stage=m.FailureStage.validate,
        failure_reason=m.FailureReason(code="MISSING_PID3", detail="no patient id"),
        message_control_id="MSGID1",
    )
    assert isinstance(dlm.dead_letter_id, UUID)
    # JSON round-trip stays stable (persistence relies on this).
    assert m.DeadLetterMessage.model_validate_json(dlm.model_dump_json()) == dlm
