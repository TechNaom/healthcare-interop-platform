"""Unit tests for the synthetic population generator (ADR-005 synthetic data)."""

from __future__ import annotations

import pytest

from hip.messaging.canonical.fhir import from_fhir_patient
from hip.messaging.canonical.mapper import map_message
from hip.messaging.hl7.parser import parse
from hip.synthetic import SyntheticPopulation

pytestmark = pytest.mark.unit


def test_deterministic_from_seed() -> None:
    a = list(SyntheticPopulation(seed=42).people(5))
    b = list(SyntheticPopulation(seed=42).people(5))
    assert a == b  # same seed -> identical population


def test_mrns_unique_across_population() -> None:
    mrns = [p.mrn for p in SyntheticPopulation(seed=1).people(50)]
    assert len(set(mrns)) == 50


def test_generated_adt_parses_and_maps() -> None:
    person = SyntheticPopulation(seed=7).person(0)
    bundle = map_message(parse(SyntheticPopulation(seed=7).hl7_adt(person)))
    assert bundle.patient is not None
    assert bundle.patient.identifiers[0].value == person.mrn
    assert bundle.encounter is not None


def test_generated_oru_maps_observation_and_report() -> None:
    pop = SyntheticPopulation(seed=7)
    person = pop.person(0)
    bundle = map_message(parse(pop.hl7_oru(person)))
    assert len(bundle.observations) == 1
    assert len(bundle.diagnostic_reports) == 1


def test_generated_fhir_patient_is_valid() -> None:
    pop = SyntheticPopulation(seed=3)
    person = pop.person(0)
    patient = from_fhir_patient(pop.fhir_patient(person))  # validates via fhir.resources
    assert patient.identifiers[0].value == person.mrn
    assert patient.administrative_sex is not None
