"""Unit tests for minimum-necessary field filtering (HIPAA 164.502(b))."""

from __future__ import annotations

import pytest

from hip.gateway.min_necessary import apply_minimum_necessary

pytestmark = [pytest.mark.unit, pytest.mark.compliance]

_PATIENT = {
    "resourceType": "Patient",
    "id": "abc",
    "identifier": [{"value": "MRN1"}],
    "name": [{"family": "DOE"}],
    "gender": "female",
    "birthDate": "1980-01-01",
    "address": [{"city": "Metro"}],
    "telecom": [{"value": "555-1212"}],
    "maritalStatus": {"text": "married"},
}


def test_full_access_returns_resource_unchanged() -> None:
    assert apply_minimum_necessary("Patient", _PATIENT, full_access=True) == _PATIENT


def test_limited_access_keeps_only_allowlisted_fields() -> None:
    out = apply_minimum_necessary("Patient", _PATIENT, full_access=False)
    assert set(out) == {"resourceType", "id", "identifier", "name", "gender", "birthDate"}
    # Restricted fields are removed, not blanked (no inference from empty).
    assert "address" not in out
    assert "telecom" not in out
    assert "maritalStatus" not in out


def test_limited_observation_hides_the_value() -> None:
    obs = {
        "resourceType": "Observation",
        "id": "o1",
        "status": "final",
        "code": {"coding": [{"code": "2339-0"}]},
        "valueQuantity": {"value": 5.4},
        "interpretation": [{"text": "H"}],
    }
    out = apply_minimum_necessary("Observation", obs, full_access=False)
    assert "valueQuantity" not in out  # the clinical result is withheld
    assert "interpretation" not in out
    assert out["code"]["coding"][0]["code"] == "2339-0"  # what was measured is kept


def test_unknown_resource_type_reduces_to_id_only() -> None:
    out = apply_minimum_necessary(
        "ServiceRequest",
        {"resourceType": "ServiceRequest", "id": "x", "secret": 1},
        full_access=False,
    )
    assert out == {"resourceType": "ServiceRequest", "id": "x"}
