"""Unit tests for HL7 v2 -> canonical mapping (ADR-001, docs/DATA_MODEL.md)."""

from __future__ import annotations

from datetime import date

import pytest

from hip.messaging.canonical import model as m
from hip.messaging.canonical.mapper import MappingError, map_message
from hip.messaging.hl7.listener import process_raw
from hip.messaging.hl7.parser import parse

pytestmark = pytest.mark.unit


def _hl7(*segments: str) -> str:
    return "\r".join(segments) + "\r"


def test_adt_maps_patient_and_encounter(adt_a01: str) -> None:
    bundle = map_message(parse(adt_a01))

    assert bundle.patient is not None
    p = bundle.patient
    assert p.identifiers[0].value == "MRN12345"
    assert p.identifiers[0].system == "HOSP"
    assert p.identifiers[0].type == "MR"
    assert p.name[0].family == "DOE"
    assert p.name[0].given == ["JANE"]
    assert p.birth_date == date(1980, 1, 1)
    assert p.administrative_sex is m.AdministrativeGender.female

    assert bundle.encounter is not None
    e = bundle.encounter
    assert e.status is m.EncounterStatus.in_progress  # derived from A01 trigger
    assert e.encounter_class is not None and e.encounter_class.code == "I"


def test_adt_discharge_derives_finished_status(adt_a01: str) -> None:
    """Encounter status comes from the trigger event, not a single field."""
    discharge = adt_a01.replace("ADT^A01", "ADT^A03").replace("EVN|A01", "EVN|A03")
    bundle = map_message(parse(discharge))
    assert bundle.encounter is not None
    assert bundle.encounter.status is m.EncounterStatus.finished


def test_oru_maps_numeric_observation(oru_r01: str) -> None:
    bundle = map_message(parse(oru_r01))
    assert len(bundle.observations) == 1
    obs = bundle.observations[0]
    assert obs.observation_code.coding[0].code == "2339-0"
    assert obs.observation_code.coding[0].display == "Glucose"
    assert isinstance(obs.value, m.Quantity)
    assert obs.value.value == 5.4
    assert obs.value.unit == "mmol/L"
    assert obs.status is m.ObservationStatus.final
    assert obs.interpretation == ["N"]
    assert obs.reference_range == "3.9-5.8"


def test_oru_coded_and_text_values() -> None:
    """OBX-5 type is driven by OBX-2 — coded (CE) and text (ST), not just numeric."""
    msg = _hl7(
        "MSH|^~\\&|LAB|LF|RA|RF|20260825101500||ORU^R01|MID1|P|2.5",
        "PID|1||MRN1^^^HOSP^MR||DOE^JANE||19800101|F",
        "OBX|1|CE|664-3^Smoker^LN||266927001^Unknown^SCT||||||F",
        "OBX|2|ST|48767-8^Comment^LN||within normal limits||||||F",
    )
    obs = map_message(parse(msg)).observations
    assert isinstance(obs[0].value, m.CodeableConcept)
    assert obs[0].value.coding[0].code == "266927001"
    assert obs[1].value == "within normal limits"


def test_unmapped_obx2_type_raises_mapping_error() -> None:
    msg = _hl7(
        "MSH|^~\\&|LAB|LF|RA|RF|20260825101500||ORU^R01|MID1|P|2.5",
        "PID|1||MRN1^^^HOSP^MR||DOE^JANE||19800101|F",
        "OBX|1|ZZ|1^x^L||whatever||||||F",
    )
    with pytest.raises(MappingError) as exc:
        map_message(parse(msg))
    assert exc.value.reason == "UNMAPPED_OBX2_TYPE"


def test_orm_maps_order_with_status_derivation() -> None:
    msg = _hl7(
        "MSH|^~\\&|OE|OF|RA|RF|20260825101500||ORM^O01|MID2|P|2.5",
        "PID|1||MRN1^^^HOSP^MR||DOE^JANE||19800101|F",
        "ORC|NW|PLAC1|FILL1|||||||||DR^WHO",
        "OBR|1|PLAC1|FILL1|2339-0^Glucose^LN",
    )
    bundle = map_message(parse(msg))
    assert len(bundle.orders) == 1
    order = bundle.orders[0]
    assert order.placer_order_number is not None and order.placer_order_number.value == "PLAC1"
    assert order.filler_order_number is not None and order.filler_order_number.value == "FILL1"
    assert order.order_control == "NW"
    assert order.status is m.RequestStatus.active  # ORC-1 NW, no ORC-5
    assert order.ordered_item is not None and order.ordered_item.coding[0].code == "2339-0"


def test_pipeline_maps_accepted_message_to_bundle(adt_a01: str) -> None:
    result = process_raw(adt_a01)
    assert result.ack_code.value == "AA"
    assert result.bundle is not None
    assert result.bundle.patient is not None


def test_pipeline_mapping_failure_is_ae_nack() -> None:
    """A transform-stage failure yields an AE NACK, not a crash."""
    msg = _hl7(
        "MSH|^~\\&|LAB|LF|RA|RF|20260825101500||ORU^R01|MID9|P|2.5",
        "PID|1||MRN1^^^HOSP^MR||DOE^JANE||19800101|F",
        "OBX|1|ZZ|1^x^L||bad||||||F",
    )
    result = process_raw(msg)
    assert result.ack_code.value == "AE"
    assert result.reason == "UNMAPPED_OBX2_TYPE"
