"""Synthetic patient population — deterministic, fully fake test/demo data.

Generates a reproducible population of synthetic people and renders them as
either HL7 v2 messages (for MLLP ingestion load) or FHIR Patient resources (for
gateway API load / demo seeding). This is the "Synthea population" the perf and
demo tooling drive; a self-contained generator is used instead of the external
Synthea tool so the population is reproducible from a seed with no extra runtime.

ABSOLUTELY NO REAL PHI (ADR-005). Every value here is drawn from small fixed
word lists and a seeded PRNG — names, dates, and identifiers are invented and
collide with real people only by coincidence. Never point this at, or seed it
from, a real data source.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any

_FAMILY = ("DOE", "ROE", "SMITH", "JONES", "PATEL", "KIM", "NGUYEN", "GARCIA", "OKAFOR", "MÜLLER")
_GIVEN = ("ALEX", "JAMIE", "SAM", "TAYLOR", "JORDAN", "CASEY", "RILEY", "MORGAN", "AVA", "NOAH")
_SEXES = ("M", "F", "O", "U")
_SEX_TO_FHIR = {"M": "male", "F": "female", "O": "other", "U": "unknown"}
# LOINC observation codes with plausible numeric ranges + units.
_OBS = (
    ("2339-0", "Glucose", 3.9, 7.8, "mmol/L"),
    ("718-7", "Hemoglobin", 12.0, 17.5, "g/dL"),
    ("2160-0", "Creatinine", 0.6, 1.3, "mg/dL"),
    ("8867-4", "Heart rate", 55.0, 100.0, "/min"),
)


@dataclass(frozen=True, slots=True)
class SyntheticPerson:
    """One invented person. ``mrn`` is unique within a generated population."""

    mrn: str
    family: str
    given: str
    sex: str  # HL7 table 0001 code
    birth_date: date

    @property
    def fhir_gender(self) -> str:
        return _SEX_TO_FHIR[self.sex]


def _hl7(*segments: str) -> str:
    """Join segments with the HL7 carriage-return separator."""
    return "\r".join(segments) + "\r"


class SyntheticPopulation:
    """Deterministic factory for synthetic people and their HL7/FHIR renderings."""

    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)  # noqa: S311 - fake data, not security-sensitive  # nosec B311

    def person(self, index: int) -> SyntheticPerson:
        """Generate the person at ``index`` (the index makes the MRN unique)."""
        year = self._rng.randint(1930, 2020)
        month = self._rng.randint(1, 12)
        day = self._rng.randint(1, 28)
        return SyntheticPerson(
            mrn=f"SYN-{index:06d}",
            family=self._rng.choice(_FAMILY),
            given=self._rng.choice(_GIVEN),
            sex=self._rng.choice(_SEXES),
            birth_date=date(year, month, day),
        )

    def people(self, count: int) -> Iterator[SyntheticPerson]:
        for i in range(count):
            yield self.person(i)

    # --- HL7 v2 renderings (for MLLP ingestion load) --------------------- #
    def _msh(self, message_type: str, control_id: str) -> str:
        return (
            f"MSH|^~\\&|SYNTHEA|SYNFAC|HIP|HIPFAC|20260101120000||{message_type}|{control_id}|P|2.5"
        )

    def _pid(self, person: SyntheticPerson) -> str:
        dob = person.birth_date.strftime("%Y%m%d")
        return f"PID|1||{person.mrn}^^^HOSP^MR||{person.family}^{person.given}||{dob}|{person.sex}"

    def hl7_adt(self, person: SyntheticPerson, *, trigger: str = "A01") -> str:
        """An ADT (admit/register) message for the person."""
        return _hl7(
            self._msh(f"ADT^{trigger}", f"ADT-{person.mrn}"),
            self._pid(person),
            "PV1|1|I|WARD^101^A|||||||||||||||||",
        )

    def hl7_oru(self, person: SyntheticPerson) -> str:
        """An ORU (lab result) message with one random observation."""
        code, name, low, high, unit = self._rng.choice(_OBS)
        value = round(self._rng.uniform(low, high), 1)
        return _hl7(
            self._msh("ORU^R01", f"ORU-{person.mrn}"),
            self._pid(person),
            f"OBR|1|PLAC-{person.mrn}|FILL-{person.mrn}|{code}^{name}^LN|||||||||||||||||||||F",
            f"OBX|1|NM|{code}^{name}^LN||{value}|{unit}|{low}-{high}|N|||F",
        )

    # --- FHIR renderings (for gateway API load / demo seeding) ----------- #
    def fhir_patient(self, person: SyntheticPerson) -> dict[str, Any]:
        """A FHIR R4 Patient resource for the person."""
        return {
            "resourceType": "Patient",
            "identifier": [
                {"system": "HOSP", "value": person.mrn, "type": {"coding": [{"code": "MR"}]}}
            ],
            "name": [{"use": "official", "family": person.family, "given": [person.given]}],
            "gender": person.fhir_gender,
            "birthDate": person.birth_date.isoformat(),
        }
