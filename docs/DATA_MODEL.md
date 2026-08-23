# Canonical data model

**Status:** Draft for review — per [ADR-001](DECISIONS.md#adr-001), this must be signed off before any ingestion or API code is written against it.

## Why a canonical model

HL7 v2 and FHIR R4/R5 both map to and from one internal representation, instead of writing HL7→FHIR and FHIR→HL7 translators directly against each other. Pairwise translation looks faster on day one and becomes an N×M maintenance problem the moment a second message type, a second FHIR version, or a vendor quirk shows up. One model, two edges in, two edges out.

## Core entities — initial scope

Scoped to what ADT, ORM, and ORU actually carry, per [SRS FR-1.2](SRS.md#51-hl7-v2-ingestion).

### Patient

| Canonical field | HL7 v2 source | FHIR R4 target |
|---|---|---|
| `patient_id` | PID-3 (Patient Identifier List) | `Patient.identifier` |
| `name` (family, given) | PID-5 | `Patient.name` |
| `birth_date` | PID-7 | `Patient.birthDate` |
| `administrative_sex` | PID-8 | `Patient.gender` |
| `address` | PID-11 | `Patient.address` |
| `phone` | PID-13 | `Patient.telecom` |
| `marital_status` | PID-16 | `Patient.maritalStatus` |
| `race` / `ethnicity` | PID-10, PID-22 (or local Z-segment) | `Patient.extension` (US Core race/ethnicity) |

### Encounter

| Canonical field | HL7 v2 source | FHIR R4 target |
|---|---|---|
| `encounter_id` | PV1-19 | `Encounter.identifier` |
| `class` (inpatient/outpatient/emergency) | PV1-2 | `Encounter.class` |
| `admit_source` | PV1-14 | `Encounter.hospitalization.admitSource` |
| `attending_provider` | PV1-7 | `Encounter.participant` |
| `location` | PV1-3 | `Encounter.location` |
| `period` (start/end) | EVN-2, PV1-45 | `Encounter.period` |
| `patient_ref` | PID-3 (via message context) | `Encounter.subject` |

### Order (ORM → FHIR ServiceRequest / MedicationRequest)

| Canonical field | HL7 v2 source | FHIR R4 target |
|---|---|---|
| `order_id` | ORC-2 (Placer) / ORC-3 (Filler) | `ServiceRequest.identifier` |
| `status` | ORC-1, ORC-5 | `ServiceRequest.status` |
| `ordered_item` | OBR-4 | `ServiceRequest.code` |
| `ordering_provider` | ORC-12 | `ServiceRequest.requester` |
| `priority` | ORC-7 | `ServiceRequest.priority` |
| `patient_ref` / `encounter_ref` | PID-3 / PV1-19 (message context) | `ServiceRequest.subject` / `.encounter` |

### Observation (ORU → FHIR Observation)

| Canonical field | HL7 v2 source | FHIR R4 target |
|---|---|---|
| `observation_id` | OBX-3 (Observation Identifier) | `Observation.identifier` |
| `value` + `unit` | OBX-5, OBX-6 | `Observation.valueQuantity` |
| `status` | OBX-11 | `Observation.status` |
| `effective_time` | OBX-14 | `Observation.effectiveDateTime` |
| `result_status` | OBR-25 | `Observation.status` (cross-checked with OBX-11) |
| `patient_ref` / `encounter_ref` | PID-3 / PV1-19 | `Observation.subject` / `.encounter` |

## Identifiers & versioning

- Canonical entities carry their own internal `canonical_id` (UUID), distinct from source-system identifiers, which are retained as `identifier` arrays (system + value) so round-tripping back to the source system stays possible.
- Canonical model schema itself is versioned (`schema_version` field) so future field additions don't silently break older stored instances.

## Data classification & storage separation

Every canonical entity instance is written to exactly one of three stores (never copied loosely between them outside the defined pipelines):

| Store | Contents | Access |
|---|---|---|
| **PHI store** | Full canonical instances, encrypted at rest | RBAC + field-level filtering; every access audited |
| **Audit log** | Append-only record of every PHI access/mutation | Auditor role; write path only from the persistence layer itself |
| **De-identified store** | Safe Harbor output of designated entities | Analytics/AI consumers; no path back to PHI store |

## What's explicitly deferred

- Full FHIR R4 resource coverage beyond Patient/Encounter/ServiceRequest/Observation — later hardening, once vendor-specific quirks are known (per [SRS §9](SRS.md#9-constraints--assumptions), EHR vendor is currently a generic assumption).
- FHIR R5-specific field differences — R5 support is a target, but the mapping table above is written against R4 first since that's the dominant deployed version.
- Local Z-segment handling — vendor-specific, deferred with the vendor-profile assumption.
