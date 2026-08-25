"""De-identification completeness (HIPAA Safe Harbor, docs/TEST_STRATEGY.md 4).

Seed a Patient carrying every removable Safe Harbor category, then assert the
de-identified copy carries none — while retaining non-identifying demographics.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from hip.messaging.canonical import model as m
from hip.security.deid import deidentify_patient, patient_safe_harbor_violations

pytestmark = [pytest.mark.unit, pytest.mark.compliance]

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _fully_identified_patient(**overrides: object) -> m.Patient:
    data: dict[str, object] = {
        "identifiers": [
            m.Identifier(value="MRN12345", system="HOSP", type="MR"),
            m.Identifier(value="123-45-6789", type="SS"),  # SSN
        ],
        "account_number": m.Identifier(value="ACCT-1", type="AN"),
        "name": [m.HumanName(family="DOE", given=["JANE"])],
        "telecom": [
            m.ContactPoint(system=m.ContactPointSystem.phone, value="555-1212"),
            m.ContactPoint(system=m.ContactPointSystem.email, value="jane@example.com"),
        ],
        "address": [
            m.Address(lines=["123 Main St"], city="Metropolis", state="NY", postal_code="10001")
        ],
        "birth_date": date(1980, 6, 15),
        "administrative_sex": m.AdministrativeGender.female,
        "marital_status": m.CodeableConcept(text="married"),
        "race": m.CodeableConcept(text="asian"),
        "ethnicity": m.CodeableConcept(text="non-hispanic"),
    }
    data.update(overrides)
    return m.Patient(**data)  # type: ignore[arg-type]


def test_deidentified_patient_has_no_safe_harbor_identifiers() -> None:
    deid = deidentify_patient(_fully_identified_patient(), now=_NOW)
    assert patient_safe_harbor_violations(deid) == []
    assert not deid.identifiers
    assert deid.account_number is None
    assert not deid.name
    assert not deid.telecom


def test_new_id_breaks_link_to_phi_record() -> None:
    original = _fully_identified_patient()
    deid = deidentify_patient(original, now=_NOW)
    assert deid.canonical_id != original.canonical_id


def test_address_generalized_to_state_and_zip3() -> None:
    deid = deidentify_patient(_fully_identified_patient(), now=_NOW)
    addr = deid.address[0]
    assert addr.state == "NY"
    assert addr.postal_code == "100"  # first 3 digits only
    assert not addr.lines
    assert addr.city is None


def test_restricted_zip_prefix_becomes_000() -> None:
    patient = _fully_identified_patient(
        address=[m.Address(state="NH", postal_code="03601")]  # 036 is restricted
    )
    deid = deidentify_patient(patient, now=_NOW)
    assert deid.address[0].postal_code == "000"


def test_birth_date_reduced_to_year() -> None:
    deid = deidentify_patient(_fully_identified_patient(), now=_NOW)
    assert deid.birth_date == date(1980, 1, 1)


def test_age_over_89_drops_birth_date() -> None:
    old = _fully_identified_patient(birth_date=date(1900, 3, 4))  # ~126y at _NOW
    deid = deidentify_patient(old, now=_NOW)
    assert deid.birth_date is None


def test_deceased_datetime_reduced_to_year() -> None:
    patient = _fully_identified_patient(deceased=True, deceased_datetime=datetime(2020, 5, 15))
    deid = deidentify_patient(patient, now=_NOW)
    assert deid.deceased_datetime is not None
    assert (deid.deceased_datetime.year, deid.deceased_datetime.month) == (2020, 1)


def test_non_identifying_demographics_retained() -> None:
    deid = deidentify_patient(_fully_identified_patient(), now=_NOW)
    assert deid.administrative_sex is m.AdministrativeGender.female
    assert deid.marital_status is not None
    assert deid.race is not None
    assert deid.ethnicity is not None
