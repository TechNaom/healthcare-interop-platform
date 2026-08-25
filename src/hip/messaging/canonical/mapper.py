"""HL7 v2 -> canonical model mapping (ADR-001, docs/DATA_MODEL.md v0.2.0).

The single highest-leverage module: everything maps through the canonical model,
never HL7->FHIR directly. This side maps parsed HL7 v2 segments to the canonical
types in ``model``; the FHIR side (canonical->FHIR) is a later phase.

Scope now: the fields DATA_MODEL.md v0.2.0 marks as initial scope for ADT
(Patient + Encounter), ORU (Observation), and ORM (Order). Vocabulary tables
(HL7 -> FHIR) are small inline maps here and become versioned configuration
later (docs/DATA_MODEL.md "Identifiers & versioning"). Deferred per DATA_MODEL:
race/ethnicity extensions, DiagnosticReport/OBR-25, local Z-segments.

A field this build cannot map safely (e.g. an unmapped OBX-2 data type) raises
``MappingError`` — the caller turns that into a transform-stage dead-letter,
never a silent coercion (docs/DATA_MODEL.md "Polymorphic observation values").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from hip.messaging.canonical import model as m
from hip.messaging.hl7.parser import ParsedMessage


class MappingError(Exception):
    """Raised when a segment can't be mapped to canonical (transform stage)."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(slots=True)
class CanonicalBundle:
    """The canonical entities produced from one HL7 message."""

    patient: m.Patient | None = None
    encounter: m.Encounter | None = None
    orders: list[m.Order] = field(default_factory=list)
    observations: list[m.Observation] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# HL7 field access (default delimiters ^~\& — alternate-delimiter handling is a
# documented later edge case, docs/TEST_STRATEGY.md tier 2)
# --------------------------------------------------------------------------- #
class _Seg:
    """Positional accessor over one HL7 segment's ``|``-split fields.

    For non-MSH segments, field N is index N (index 0 is the segment name).
    """

    __slots__ = ("fields",)

    def __init__(self, fields: list[str]) -> None:
        self.fields = fields

    def field(self, n: int) -> str:
        return self.fields[n].strip() if n < len(self.fields) else ""

    def comp(self, n: int, c: int) -> str:
        parts = self.field(n).split("^")
        return parts[c - 1].strip() if 0 < c <= len(parts) else ""

    def reps(self, n: int) -> list[str]:
        raw = self.field(n)
        return [r for r in raw.split("~") if r] if raw else []


def _segments(raw: str) -> dict[str, list[_Seg]]:
    text = raw.replace("\r\n", "\r").replace("\n", "\r").strip()
    out: dict[str, list[_Seg]] = {}
    for line in (s for s in text.split("\r") if s):
        fields = line.split("|")
        out.setdefault(fields[0], []).append(_Seg(fields))
    return out


def _first(segs: dict[str, list[_Seg]], name: str) -> _Seg | None:
    got = segs.get(name)
    return got[0] if got else None


def _parse_ts(value: str) -> datetime | None:
    """HL7 TS (YYYYMMDD[HHMM[SS]][+/-ZZZZ]) -> datetime (tz offset dropped)."""
    digits = "".join(ch for ch in value if ch.isdigit())
    for fmt, length in (("%Y%m%d%H%M%S", 14), ("%Y%m%d%H%M", 12), ("%Y%m%d", 8)):
        if len(digits) >= length:
            try:
                return datetime.strptime(digits[:length], fmt)  # noqa: DTZ007
            except ValueError:
                continue
    return None


def _parse_date(value: str) -> date | None:
    v = value.strip()[:8]
    try:
        return datetime.strptime(v, "%Y%m%d").date()  # noqa: DTZ007
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Vocabulary maps (HL7 table -> FHIR value set). Small now; versioned config later.
# --------------------------------------------------------------------------- #
_GENDER = {  # HL7 table 0001 -> FHIR administrative-gender
    "M": m.AdministrativeGender.male,
    "F": m.AdministrativeGender.female,
    "O": m.AdministrativeGender.other,
    "A": m.AdministrativeGender.other,
    "N": m.AdministrativeGender.other,
    "U": m.AdministrativeGender.unknown,
}

# ADT trigger event -> Encounter.status (docs/DATA_MODEL.md: status derived from
# the message trigger, not a single field).
_ENCOUNTER_STATUS = {
    "A01": m.EncounterStatus.in_progress,  # admit
    "A02": m.EncounterStatus.in_progress,  # transfer
    "A03": m.EncounterStatus.finished,  # discharge
    "A04": m.EncounterStatus.in_progress,  # register
    "A08": m.EncounterStatus.in_progress,  # update
    "A11": m.EncounterStatus.cancelled,  # cancel admit
    "A13": m.EncounterStatus.in_progress,  # cancel discharge
}

_OBS_STATUS = {  # HL7 table 0085 -> FHIR observation-status
    "F": m.ObservationStatus.final,
    "P": m.ObservationStatus.preliminary,
    "C": m.ObservationStatus.corrected,
    "R": m.ObservationStatus.registered,
    "X": m.ObservationStatus.cancelled,
    "D": m.ObservationStatus.entered_in_error,
}

# ORC-1 order control -> RequestStatus, used only when ORC-5 is not valued
# (docs/DATA_MODEL.md "Order status derivation").
_ORDER_CONTROL_STATUS = {
    "NW": m.RequestStatus.active,
    "OK": m.RequestStatus.active,
    "CA": m.RequestStatus.revoked,
    "OC": m.RequestStatus.revoked,
    "DC": m.RequestStatus.revoked,
    "CM": m.RequestStatus.completed,
    "HD": m.RequestStatus.on_hold,
}

_ORC5_STATUS = {  # HL7 table 0038 (ORC-5) -> RequestStatus (authoritative)
    "SC": m.RequestStatus.active,
    "IP": m.RequestStatus.active,
    "A": m.RequestStatus.active,
    "CM": m.RequestStatus.completed,
    "CA": m.RequestStatus.revoked,
    "DC": m.RequestStatus.revoked,
    "HD": m.RequestStatus.on_hold,
}

# OBX-2 data type -> how OBX-5 is carried (docs/DATA_MODEL.md polymorphic values).
_NUMERIC_TYPES = {"NM", "SN"}
_STRING_TYPES = {"ST", "TX", "FT"}
_CODED_TYPES = {"CE", "CWE", "CNE"}
_DATETIME_TYPES = {"DT", "TS", "DTM"}


# --------------------------------------------------------------------------- #
# Entity mappers
# --------------------------------------------------------------------------- #
def _identifier(seg: _Seg, n: int, *, type_code: str | None = None) -> m.Identifier | None:
    value = seg.comp(n, 1)
    if not value:
        return None
    return m.Identifier(
        value=value,
        system=seg.comp(n, 4) or None,  # assigning authority
        type=type_code or (seg.comp(n, 5) or None),
    )


def _get(parts: list[str], index: int) -> str:
    """Safe positional access into a delimited component list."""
    return parts[index].strip() if index < len(parts) else ""


def _provider_ref(value: str) -> m.Reference | None:
    """A Practitioner reference from an HL7 XCN provider field (display only)."""
    display = value.replace("^", " ").strip()
    return m.Reference(type="Practitioner", display=display) if display else None


def _identifier_from_rep(rep: str) -> m.Identifier | None:
    """Build an Identifier from a repetition string (CX: id^^^authority^type)."""
    parts = [p.strip() for p in rep.split("^")]
    if not _get(parts, 0):
        return None
    return m.Identifier(
        value=parts[0].strip(),
        system=_get(parts, 3) or None,
        type=_get(parts, 4) or None,
    )


def _human_name(rep: str) -> m.HumanName:
    """Map an HL7 XPN (family^given^middle^suffix^prefix^degree^name-type)."""
    c = [p.strip() for p in rep.split("^")]

    def part(idx: int) -> str:
        return c[idx] if idx < len(c) else ""

    use = part(6)
    return m.HumanName(
        family=part(0) or None,
        given=[part(1)] if part(1) else [],
        suffix=[part(3)] if part(3) else [],
        prefix=[part(4)] if part(4) else [],
        use=m.NameUse.legal if use in ("", "L") else None,
    )


def map_patient(segs: dict[str, list[_Seg]]) -> m.Patient | None:
    pid = _first(segs, "PID")
    if pid is None:
        return None

    identifiers = [i for rep in pid.reps(3) if (i := _identifier_from_rep(rep)) is not None]
    names = [_human_name(rep) for rep in pid.reps(5)]

    addresses: list[m.Address] = []
    if pid.field(11):
        addresses.append(
            m.Address(
                lines=[x for x in (pid.comp(11, 1), pid.comp(11, 2)) if x],
                city=pid.comp(11, 3) or None,
                state=pid.comp(11, 4) or None,
                postal_code=pid.comp(11, 5) or None,
                country=pid.comp(11, 6) or None,
            )
        )

    telecom: list[m.ContactPoint] = []
    if pid.comp(13, 1) or pid.field(13):
        telecom.append(
            m.ContactPoint(
                system=m.ContactPointSystem.phone,
                value=pid.comp(13, 1) or pid.field(13),
                use=m.ContactPointUse.home,
            )
        )
    if pid.comp(14, 1) or pid.field(14):
        telecom.append(
            m.ContactPoint(
                system=m.ContactPointSystem.phone,
                value=pid.comp(14, 1) or pid.field(14),
                use=m.ContactPointUse.work,
            )
        )

    return m.Patient(
        identifiers=identifiers,
        name=names,
        birth_date=_parse_date(pid.field(7)),
        administrative_sex=_GENDER.get(pid.field(8).upper()) if pid.field(8) else None,
        address=addresses,
        telecom=telecom,
        account_number=_identifier(pid, 18, type_code="AN"),
    )


def map_encounter(segs: dict[str, list[_Seg]], trigger_event: str) -> m.Encounter | None:
    pv1 = _first(segs, "PV1")
    if pv1 is None:
        return None
    pid = _first(segs, "PID")

    locations: list[m.EncounterLocation] = []
    if pv1.field(3):
        locations.append(
            m.EncounterLocation(
                location=m.Reference(
                    type="Location", display=pv1.field(3).replace("^", " ").strip()
                )
            )
        )

    return m.Encounter(
        visit_number=_identifier(pv1, 19),
        account_number=_identifier(pid, 18, type_code="AN") if pid else None,
        encounter_class=m.Coding(code=pv1.field(2)) if pv1.field(2) else None,
        status=_ENCOUNTER_STATUS.get(trigger_event),
        attending_provider=_provider_ref(pv1.field(7)),
        referring_provider=_provider_ref(pv1.field(8)),
        locations=locations,
        period=m.Period(start=_parse_ts(pv1.field(44)), end=_parse_ts(pv1.field(45)))
        if (pv1.field(44) or pv1.field(45))
        else None,
    )


def _codeable(seg: _Seg, n: int) -> m.CodeableConcept | None:
    code = seg.comp(n, 1)
    if not code:
        return None
    return m.CodeableConcept(
        coding=[m.Coding(code=code, display=seg.comp(n, 2) or None, system=seg.comp(n, 3) or None)]
    )


def _observation_value(obx: _Seg) -> m.ObservationValue | None:
    obx2 = obx.field(2).upper()
    obx5 = obx.field(5)
    if not obx5:
        return None
    if obx2 in _NUMERIC_TYPES:
        try:
            return m.Quantity(value=float(obx.comp(5, 1) or obx5), unit=obx.comp(6, 1) or None)
        except ValueError as exc:
            raise MappingError("BAD_NUMERIC_VALUE", f"OBX-5 {obx5!r} not numeric") from exc
    if obx2 in _STRING_TYPES:
        return obx5
    if obx2 in _CODED_TYPES:
        return _codeable(obx, 5)
    if obx2 in _DATETIME_TYPES:
        return _parse_ts(obx5)
    raise MappingError("UNMAPPED_OBX2_TYPE", f"OBX-2 data type {obx2!r} has no mapping")


def map_observations(segs: dict[str, list[_Seg]]) -> list[m.Observation]:
    out: list[m.Observation] = []
    for obx in segs.get("OBX", []):
        code = _codeable(obx, 3)
        if code is None:
            raise MappingError("MISSING_OBX3", "OBX-3 (observation code) is required")
        out.append(
            m.Observation(
                observation_code=code,
                value_type=obx.field(2) or None,
                value=_observation_value(obx),
                unit=obx.comp(6, 1) or None,
                reference_range=obx.field(7) or None,
                interpretation=obx.reps(8),
                status=_OBS_STATUS.get(obx.field(11).upper()) if obx.field(11) else None,
                effective_time=_parse_ts(obx.field(14)),
            )
        )
    return out


def map_orders(segs: dict[str, list[_Seg]]) -> list[m.Order]:
    orders: list[m.Order] = []
    orcs = segs.get("ORC", [])
    obrs = segs.get("OBR", [])
    for i, orc in enumerate(orcs):
        obr = obrs[i] if i < len(obrs) else None
        orc5 = orc.field(5).upper()
        orc1 = orc.field(1).upper()
        status = _ORC5_STATUS.get(orc5) if orc5 else _ORDER_CONTROL_STATUS.get(orc1)
        orders.append(
            m.Order(
                placer_order_number=_identifier(orc, 2, type_code="PLAC"),
                filler_order_number=_identifier(orc, 3, type_code="FILL"),
                order_control=orc1 or None,
                status=status,
                ordered_item=_codeable(obr, 4) if obr else None,
                ordering_provider=_provider_ref(orc.field(12)),
                order_datetime=_parse_ts(orc.field(9)),
            )
        )
    return orders


def map_message(parsed: ParsedMessage) -> CanonicalBundle:
    """Map a parsed HL7 message to canonical entities, dispatched by type.

    Raises ``MappingError`` if a segment can't be mapped safely.
    """
    segs = _segments(parsed.raw)
    bundle = CanonicalBundle(patient=map_patient(segs))

    if parsed.message_code == "ADT":
        bundle.encounter = map_encounter(segs, parsed.trigger_event)
    elif parsed.message_code == "ORM":
        bundle.orders = map_orders(segs)
    elif parsed.message_code == "ORU":
        bundle.observations = map_observations(segs)
        bundle.orders = map_orders(segs)  # ORU may carry ORC/OBR context

    return bundle
