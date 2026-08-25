"""Canonical data model — Pydantic v2 types (ADR-001, docs/DATA_MODEL.md v0.2.0).

The single internal representation that HL7 v2 and FHIR R4/R5 both map to and
from. Every ingestion/API/persistence path targets these types, never the wire
formats directly. This module is the reviewable ADR-001 deliverable; the
`mapper` module stays a stub until these types are signed off.

Field-by-field provenance (HL7 v2 source, FHIR R4 target) is in
docs/DATA_MODEL.md — kept there rather than duplicated in every docstring, so
there is one source of truth for the mappings. Where a field needs vocabulary
mapping (HL7 table -> FHIR ValueSet) it is typed as a `Coding`/`CodeableConcept`
here and the mapping itself is versioned configuration, not hardcoded.

Placement note: the canonical model lives under `hip.messaging.canonical` to
match the documented module map (docs/DESIGN.md 1). Gateway and persistence
depend on these types; the dependency direction (edges -> canonical) is
deliberate and one-way.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

# Canonical schema version — bump when fields change so stored instances stay
# interpretable (docs/DATA_MODEL.md "Identifiers & versioning").
CANONICAL_SCHEMA_VERSION = "0.2.0"


class _Base(BaseModel):
    """Shared config: reject unknown fields so mapping typos fail loudly."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Value objects
# --------------------------------------------------------------------------- #
class IdentifierUse(StrEnum):
    usual = "usual"
    official = "official"
    temp = "temp"
    secondary = "secondary"
    old = "old"


class Identifier(_Base):
    """A source-system identifier, retained with its assigning authority.

    Kept as (system, value, type) so round-tripping back to the source system
    stays possible (docs/DATA_MODEL.md). ``type`` carries HL7 identifier-type
    codes such as ``AN`` (account), ``PLAC``/``FILL`` (placer/filler order).
    """

    system: str | None = None
    value: str
    type: str | None = None
    use: IdentifierUse | None = None


class NameUse(StrEnum):
    legal = "legal"
    alias = "alias"
    maiden = "maiden"
    official = "official"
    usual = "usual"


class HumanName(_Base):
    family: str | None = None
    given: list[str] = Field(default_factory=list)
    prefix: list[str] = Field(default_factory=list)
    suffix: list[str] = Field(default_factory=list)
    use: NameUse | None = None


class ContactPointSystem(StrEnum):
    phone = "phone"
    fax = "fax"
    email = "email"
    pager = "pager"
    other = "other"


class ContactPointUse(StrEnum):
    home = "home"
    work = "work"
    mobile = "mobile"
    temp = "temp"
    old = "old"


class ContactPoint(_Base):
    system: ContactPointSystem | None = None
    value: str
    use: ContactPointUse | None = None


class AddressUse(StrEnum):
    home = "home"
    work = "work"
    temp = "temp"
    billing = "billing"


class Address(_Base):
    lines: list[str] = Field(default_factory=list)
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    use: AddressUse | None = None


class Coding(_Base):
    """A single coded value from a code system (the unit of vocabulary mapping)."""

    system: str | None = None
    code: str
    display: str | None = None


class CodeableConcept(_Base):
    coding: list[Coding] = Field(default_factory=list)
    text: str | None = None


class Quantity(_Base):
    value: float
    unit: str | None = None
    system: str | None = None
    code: str | None = None
    comparator: str | None = None  # <, <=, >=, > (SN structured numerics)


class Period(_Base):
    start: datetime | None = None
    end: datetime | None = None


class Reference(_Base):
    """A reference to another canonical entity.

    Carries the target's ``canonical_id`` when known and/or a source
    ``identifier`` for context (e.g. the PID-3 / PV1-19 that appeared in the
    message), plus the target entity ``type`` (``Patient``, ``Encounter``, ...).
    """

    type: str
    canonical_id: UUID | None = None
    identifier: Identifier | None = None
    display: str | None = None


# --------------------------------------------------------------------------- #
# Domain vocabularies (fixed FHIR value sets; hyphenated codes preserved)
# --------------------------------------------------------------------------- #
class AdministrativeGender(StrEnum):
    male = "male"
    female = "female"
    other = "other"
    unknown = "unknown"


class EncounterStatus(StrEnum):
    planned = "planned"
    arrived = "arrived"
    triaged = "triaged"
    in_progress = "in-progress"
    onleave = "onleave"
    finished = "finished"
    cancelled = "cancelled"
    entered_in_error = "entered-in-error"
    unknown = "unknown"


class RequestStatus(StrEnum):
    draft = "draft"
    active = "active"
    on_hold = "on-hold"
    revoked = "revoked"
    completed = "completed"
    entered_in_error = "entered-in-error"
    unknown = "unknown"


class RequestIntent(StrEnum):
    proposal = "proposal"
    plan = "plan"
    order = "order"
    original_order = "original-order"
    reflex_order = "reflex-order"


class ObservationStatus(StrEnum):
    registered = "registered"
    preliminary = "preliminary"
    final = "final"
    amended = "amended"
    corrected = "corrected"
    cancelled = "cancelled"
    entered_in_error = "entered-in-error"
    unknown = "unknown"


class FailureStage(StrEnum):
    parse = "parse"
    validate = "validate"
    transform = "transform"
    persist = "persist"


# The polymorphic Observation value (OBX-5), selected by OBX-2 (docs/DATA_MODEL.md
# "Polymorphic observation values"). Order matters for pydantic's smart union:
# structured types before the str fallback.
ObservationValue = Quantity | CodeableConcept | datetime | bool | int | float | str


# --------------------------------------------------------------------------- #
# Canonical resources
# --------------------------------------------------------------------------- #
class CanonicalResource(_Base):
    """Common base: an internal id distinct from source identifiers, plus schema
    version so field additions don't silently break stored instances."""

    canonical_id: UUID = Field(default_factory=uuid4)
    schema_version: str = CANONICAL_SCHEMA_VERSION
    # PID-3 style source identifier list; assigning authority retained per entry.
    identifiers: list[Identifier] = Field(default_factory=list)


class Patient(CanonicalResource):
    name: list[HumanName] = Field(default_factory=list)
    birth_date: date | None = None
    administrative_sex: AdministrativeGender | None = None
    address: list[Address] = Field(default_factory=list)
    telecom: list[ContactPoint] = Field(default_factory=list)
    marital_status: CodeableConcept | None = None
    deceased: bool | None = None
    deceased_datetime: datetime | None = None
    race: CodeableConcept | None = None
    ethnicity: CodeableConcept | None = None
    # PID-18; also participates in encounter identity (see Encounter).
    account_number: Identifier | None = None


class EncounterLocation(_Base):
    location: Reference
    period: Period | None = None


class IdentitySource(StrEnum):
    """Which identifier is authoritative for an encounter — a per-source
    configuration value, never hardcoded (docs/DATA_MODEL.md "Encounter identity")."""

    visit_number = "visit_number"
    account_number = "account_number"


class Encounter(CanonicalResource):
    visit_number: Identifier | None = None  # PV1-19
    account_number: Identifier | None = None  # PID-18
    identity_source: IdentitySource | None = None
    encounter_class: Coding | None = None  # PV1-2 (FHIR `class`)
    status: EncounterStatus | None = None  # derived from trigger event + PV1-2
    admit_source: CodeableConcept | None = None
    discharge_disposition: CodeableConcept | None = None
    attending_provider: Reference | None = None  # PV1-7
    referring_provider: Reference | None = None  # PV1-8
    locations: list[EncounterLocation] = Field(default_factory=list)
    period: Period | None = None  # PV1-44 / PV1-45
    patient_ref: Reference | None = None


class Order(CanonicalResource):
    """ORM -> FHIR ServiceRequest / MedicationRequest."""

    placer_order_number: Identifier | None = None  # ORC-2
    filler_order_number: Identifier | None = None  # ORC-3
    order_control: str | None = None  # ORC-1 event code (drives status+intent)
    status: RequestStatus | None = None  # ORC-5 authoritative, else derived
    intent: RequestIntent = RequestIntent.order
    ordered_item: CodeableConcept | None = None  # OBR-4
    ordering_provider: Reference | None = None  # ORC-12
    priority: str | None = None  # ORC-7.6 / TQ1-9 (vocabulary mapping)
    order_datetime: datetime | None = None  # ORC-9
    patient_ref: Reference | None = None
    encounter_ref: Reference | None = None


class Observation(CanonicalResource):
    """ORU -> FHIR Observation. ``observation_code`` (OBX-3) is the central field
    — what was measured — and is required."""

    observation_code: CodeableConcept  # OBX-3
    value_type: str | None = None  # OBX-2 (selects which value[x] applies)
    value: ObservationValue | None = None  # OBX-5
    unit: str | None = None  # OBX-6 (only when value_type is NM/SN)
    reference_range: str | None = None  # OBX-7
    interpretation: list[str] = Field(default_factory=list)  # OBX-8 abnormal flags
    status: ObservationStatus | None = None  # OBX-11
    effective_time: datetime | None = None  # OBX-14
    performer: Reference | None = None  # OBX-16
    patient_ref: Reference | None = None
    encounter_ref: Reference | None = None


class FailureReason(_Base):
    code: str
    detail: str | None = None


class DeadLetterMessage(_Base):
    """An unprocessable raw message.

    CLASSIFICATION: this holds the raw HL7 payload, which contains PHI. The
    dead-letter store is therefore a PHI store — encrypted, access-audited, same
    retention as any PHI. It is NOT a debug log (docs/DATA_MODEL.md).
    """

    dead_letter_id: UUID = Field(default_factory=uuid4)
    received_at: datetime
    source: str | None = None  # MSH-3 / MSH-4
    raw_message: str  # PHI
    failure_stage: FailureStage
    failure_reason: FailureReason
    message_control_id: str | None = None  # MSH-10
