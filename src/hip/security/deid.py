"""Safe Harbor de-identification (HIPAA 164.514(b)).

Maps to ``security.deid`` in docs/DESIGN.md 1. Produces a de-identified COPY of a
canonical resource — a new instance with a fresh ``canonical_id`` and no reverse
path to the PHI record (docs/DATA_MODEL.md flow invariant). The 18 Safe Harbor
identifier categories are removed or generalized; demographics that are not
identifiers (sex, marital status, race, ethnicity) are retained for analytics.

Scope now: Patient (the identifier-bearing resource). Encounter/Observation
follow the same remove-identifiers / generalize-dates pattern.

Structured Safe Harbor only. NER-based de-identification of free-text is a
documented future phase (roadmap "out of scope").
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from hip.messaging.canonical import model as m

# HIPAA "3-digit ZIP" rule: these prefixes cover areas of <=20,000 people and
# must be reported as 000 (45 CFR 164.514(b)(2)(i)(B)).
_RESTRICTED_ZIP3 = frozenset(
    {
        "036",
        "059",
        "063",
        "102",
        "203",
        "556",
        "692",
        "790",
        "821",
        "823",
        "830",
        "831",
        "878",
        "879",
        "884",
        "890",
        "893",
    }
)

_MAX_AGE = 89  # ages over 89 must be aggregated to "90 or older"
_ZIP3_LEN = 3  # Safe Harbor permits only the first 3 ZIP digits


def _generalize_zip(postal_code: str | None) -> str | None:
    if not postal_code:
        return None
    digits = "".join(ch for ch in postal_code if ch.isdigit())
    if len(digits) < _ZIP3_LEN:
        return None
    zip3 = digits[:_ZIP3_LEN]
    return "000" if zip3 in _RESTRICTED_ZIP3 else zip3


def _generalize_address(address: m.Address) -> m.Address | None:
    """Keep state + generalized ZIP + country; drop street/city (smaller than state)."""
    generalized = m.Address(
        state=address.state or None,
        postal_code=_generalize_zip(address.postal_code),
        country=address.country or None,
    )
    # If nothing geographic survives, drop the address entirely.
    if not (generalized.state or generalized.postal_code or generalized.country):
        return None
    return generalized


def _year_only(value: date | None, *, now_year: int) -> date | None:
    """Keep year only; drop dates indicative of an age over 89 (90+ aggregation)."""
    if value is None:
        return None
    if now_year - value.year > _MAX_AGE:
        return None  # would reveal 90+; remove the date entirely
    return date(value.year, 1, 1)


def deidentify_patient(patient: m.Patient, *, now: datetime | None = None) -> m.Patient:
    """Return a Safe-Harbor-de-identified copy of a canonical Patient."""
    now_year = (now or datetime.now(UTC)).year

    addresses = [a for a in (_generalize_address(addr) for addr in patient.address) if a]
    birth = _year_only(patient.birth_date, now_year=now_year)
    deceased_dt = patient.deceased_datetime
    deceased_year = (
        datetime(deceased_dt.year, 1, 1, tzinfo=UTC) if deceased_dt is not None else None
    )

    return m.Patient(
        # Fresh id — no link back to the PHI instance.
        # (canonical_id defaults to a new uuid4.)
        # --- removed Safe Harbor identifiers ---
        identifiers=[],  # MRNs, SSNs, plan/account numbers, etc. (1,7,8,9,10,...)
        account_number=None,  # (10) account numbers
        name=[],  # (A) names
        telecom=[],  # (D,E,F) phone/fax/email
        # --- generalized ---
        address=addresses,  # (B) geo: state + 3-digit ZIP only
        birth_date=birth,  # (C) dates: year only; 90+ dropped
        deceased_datetime=deceased_year,
        # --- retained non-identifying demographics ---
        administrative_sex=patient.administrative_sex,
        marital_status=patient.marital_status,
        deceased=patient.deceased,
        race=patient.race,
        ethnicity=patient.ethnicity,
    )


def patient_safe_harbor_violations(patient: m.Patient) -> list[str]:
    """Return the Safe Harbor categories still present (empty == de-identified).

    Used by the compliance test to assert completeness against a record seeded
    with every category.
    """
    violations: list[str] = []
    if patient.identifiers:
        violations.append("identifiers")
    if patient.account_number is not None:
        violations.append("account_number")
    if patient.name:
        violations.append("name")
    if patient.telecom:
        violations.append("telecom")
    for addr in patient.address:
        if addr.lines or addr.city:
            violations.append("address_fine_grained")
        if addr.postal_code and len(addr.postal_code) > _ZIP3_LEN:
            violations.append("zip_full")
    if patient.birth_date is not None and (patient.birth_date.month, patient.birth_date.day) != (
        1,
        1,
    ):
        violations.append("birth_date_precise")
    return violations
