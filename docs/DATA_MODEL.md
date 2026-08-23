# Canonical data model

**Status:** Draft for review — per [ADR-001](DECISIONS.md#adr-001), this must be signed off before any ingestion or API code is written against it.
**Version:** 0.2.0 · 2026-08-24 — corrects mapping errors in 0.1.0 (see [Revision notes](#revision-notes)).

## Why a canonical model

HL7 v2 and FHIR R4/R5 both map to and from one internal representation, instead of writing HL7→FHIR and FHIR→HL7 translators directly against each other. Pairwise translation looks faster on day one and becomes an N×M maintenance problem the moment a second message type, a second FHIR version, or a vendor quirk shows up. One model, two edges in, two edges out.

Mappings below follow the official [HL7 v2-to-FHIR ConceptMaps](https://build.fhir.org/ig/HL7/v2-to-fhir/) where one exists. Where this document simplifies a mapping that is genuinely conditional in the spec, it says so explicitly rather than hiding it.

## Core entities — initial scope

Scoped to what ADT, ORM, and ORU actually carry, per [SRS §4.1](SRS.md#41-hl7-v2-message-handling).

### Patient

| Canonical field | HL7 v2 source | FHIR R4 target | Notes |
|---|---|---|---|
| `patient_id` | PID-3 (Patient Identifier List) | `Patient.identifier` | Repeating; retain all identifiers with their assigning authority, not just the first |
| `account_number` | PID-18 (Patient Account Number) | `Patient.identifier` (typed `AN`) | Also participates in encounter identity — see [Encounter identity](#encounter-identity-a-real-vendor-variation) |
| `name` (family, given, prefix, suffix) | PID-5 | `Patient.name` | Repeating; PID-5.7 name-type code distinguishes legal vs. alias |
| `birth_date` | PID-7 | `Patient.birthDate` | |
| `administrative_sex` | PID-8 | `Patient.gender` | Requires vocabulary mapping — HL7 table 0001 → FHIR `administrative-gender`; values are **not** identical |
| `address` | PID-11 | `Patient.address` | Repeating |
| `phone` | PID-13 (home), PID-14 (business) | `Patient.telecom` | Both map to telecom with different `use` values |
| `marital_status` | PID-16 | `Patient.maritalStatus` | Vocabulary mapping required |
| `deceased` (flag + datetime) | PID-30, PID-29 | `Patient.deceasedBoolean` / `deceasedDateTime` | Was missing in 0.1.0; ADT carries it and it is clinically significant |
| `race` / `ethnicity` | PID-10, PID-22 | `Patient.extension` (US Core race/ethnicity) | Vendor-specific Z-segments deferred |

### Encounter

| Canonical field | HL7 v2 source | FHIR R4 target | Notes |
|---|---|---|---|
| `visit_number` | PV1-19 (Visit Number) | `Encounter.identifier` | The per-encounter identifier |
| `account_number` | PID-18 (Patient Account Number) | `Encounter.identifier` (typed) | Billing-episode identifier; one account may span multiple visits |
| `class` | PV1-2 (Patient Class) | `Encounter.class` | Vocabulary mapping: HL7 table 0004 → FHIR `v3-ActEncounterCode` |
| `status` | PV1-2 + trigger event (A01/A03/A08…) | `Encounter.status` | Derived from the **message trigger event**, not a single field — an A01 implies `in-progress`, A03 implies `finished` |
| `admit_source` | PV1-14 | `Encounter.hospitalization.admitSource` | |
| `discharge_disposition` | PV1-36 | `Encounter.hospitalization.dischargeDisposition` | Was missing in 0.1.0 |
| `attending_provider` | PV1-7 | `Encounter.participant` (type `ATND`) | |
| `referring_provider` | PV1-8 | `Encounter.participant` (type `REF`) | |
| `location` | PV1-3 (assigned), PV1-6 (prior) | `Encounter.location` | Repeating with period |
| `period` (start/end) | PV1-44 (admit), PV1-45 (discharge) | `Encounter.period` | **Corrected from 0.1.0** — EVN-2 is the *event* timestamp, not the admit time |
| `patient_ref` | PID-3 (message context) | `Encounter.subject` | |

#### Encounter identity: a real vendor variation

PV1-19 (Visit Number) and PID-18 (Account Number) are different concepts: an *account* identifies a billing episode of care; a *visit* identifies one encounter within it. One account may have many visits.

Real systems disagree on which is the encounter identifier — [CareEvolution's HIE stack defaults to PID-18](https://hl7.docs.careevolution.com/concepts/encounter_id.html) and is reconfigurable to PV1-19. Since [SRS §12](SRS.md#12-constraints-and-assumptions) assumes generic vendors, **the canonical model carries both** and which one is authoritative for identity is a per-source configuration value, not a hardcoded assumption. Betting on one and discovering the vendor uses the other is exactly the retrofit ADR-001 exists to prevent.

### Order (ORM → FHIR ServiceRequest / MedicationRequest)

| Canonical field | HL7 v2 source | FHIR R4 target | Notes |
|---|---|---|---|
| `placer_order_number` | ORC-2 | `ServiceRequest.identifier` (typed `PLAC`) | |
| `filler_order_number` | ORC-3 | `ServiceRequest.identifier` (typed `FILL`) | Distinct identifier, not interchangeable with ORC-2 |
| `order_control` | ORC-1 (Order Control) | drives `.status` **and** `.intent` | **Corrected from 0.1.0** — see [Order status derivation](#order-status-derivation) |
| `order_status` | ORC-5 (Order Status) | `ServiceRequest.status` | Takes precedence over ORC-1 when valued |
| `ordered_item` | OBR-4 (Universal Service ID) | `ServiceRequest.code` | Vocabulary mapping to LOINC/SNOMED where available |
| `ordering_provider` | ORC-12 | `ServiceRequest.requester` | |
| `priority` | ORC-7.6 / TQ1-9 | `ServiceRequest.priority` | Vocabulary mapping required |
| `order_datetime` | ORC-9 | `ServiceRequest.authoredOn` | |
| `patient_ref` / `encounter_ref` | PID-3 / PV1-19 (message context) | `ServiceRequest.subject` / `.encounter` | |

#### Order status derivation

ORC-1 (Order Control) is an **event code** (NW = new, CA = cancel, OC = order cancelled…), not a status. Per the [official HL7 ORC→ServiceRequest ConceptMap](https://build.fhir.org/ig/HL7/v2-to-fhir/ConceptMap-segment-orc-to-servicerequest.html):

- ORC-1 → `ServiceRequest.status` **only when ORC-5 is not valued**
- ORC-1 → `ServiceRequest.intent` (typically `order`) independently
- ORC-5, when present, is the authoritative source for `.status`

Version 0.1.0 of this document listed "ORC-1, ORC-5" as joint inputs to `status`, which conflates an event code with a state and would have produced wrong statuses on cancel/hold messages. The transformation logic must implement the conditional, not pick one field.

### Observation (ORU → FHIR Observation)

| Canonical field | HL7 v2 source | FHIR R4 target | Notes |
|---|---|---|---|
| `observation_code` | **OBX-3** (Observation Identifier) | **`Observation.code`** | **Corrected from 0.1.0** — OBX-3 is *what was measured* (e.g. a LOINC code for serum glucose), not an instance identifier. 0.1.0 mapped this to `Observation.identifier`, which lost the resource's central field. |
| `observation_id` | OBR-3 + OBX-4 (sub-ID) | `Observation.identifier` | Instance identity is derived from filler order number plus observation sub-ID; HL7 v2 has no single dedicated observation-instance identifier field |
| `value_type` | OBX-2 | determines which `value[x]` applies | See [Polymorphic values](#polymorphic-observation-values) |
| `value` | OBX-5 | `Observation.valueQuantity` \| `valueString` \| `valueCodeableConcept` \| `valueBoolean` \| … | Type selected by OBX-2, **not** always Quantity |
| `unit` | OBX-6 | `Observation.valueQuantity.unit` | Only applies when `value_type` is NM/SN |
| `reference_range` | OBX-7 | `Observation.referenceRange` | Was missing in 0.1.0 |
| `abnormal_flags` | OBX-8 | `Observation.interpretation` | Was missing in 0.1.0; clinically significant |
| `observation_status` | OBX-11 | `Observation.status` | Per-observation status; authoritative for this resource |
| `effective_time` | OBX-14 | `Observation.effectiveDateTime` | |
| `performer` | OBX-16 | `Observation.performer` | |
| `patient_ref` / `encounter_ref` | PID-3 / PV1-19 | `Observation.subject` / `.encounter` | |

#### Polymorphic observation values

OBX-2 declares the data type of OBX-5. Mapping OBX-5 unconditionally to `valueQuantity` (as 0.1.0 did) rejects valid ORU messages carrying text or coded results. Minimum required handling:

| OBX-2 | FHIR target |
|---|---|
| `NM` (numeric) | `valueQuantity` |
| `SN` (structured numeric) | `valueQuantity` with comparator, or `valueRange` |
| `ST`, `TX`, `FT` (text) | `valueString` |
| `CE`, `CWE` (coded) | `valueCodeableConcept` |
| `DT`, `TS` (date/time) | `valueDateTime` |
| Unmapped type | Route to dead-letter with a specific reason code — never coerce silently |

`OBR-25` (result status) is a **report-level** status and maps to `DiagnosticReport.status`, not to individual `Observation.status`. Version 0.1.0 mapped it to `Observation.status` alongside OBX-11, which conflates report and observation scope.

### DeadLetterMessage

Not a clinical entity, but a first-class stored entity — [DESIGN.md §4](DESIGN.md#4-error-handling--ackNACK-strategy) commits to a dead-letter store and 0.1.0 defined no model for it.

| Field | Description |
|---|---|
| `dead_letter_id` | UUID |
| `received_at` | Ingestion timestamp |
| `source` | Transport + sending facility (MSH-3/MSH-4) |
| `raw_message` | Original message bytes, unmodified |
| `failure_stage` | `parse` \| `validate` \| `transform` \| `persist` |
| `failure_reason` | Structured code + human-readable detail |
| `message_control_id` | MSH-10, for correlation with the sender's records |

**Critical classification note:** a dead-letter message contains the raw HL7 payload, which contains PHI. The dead-letter store is therefore a **PHI store** — encrypted at rest, access-audited, and subject to the same retention rules as any other PHI. It is not a debug log and must never be treated as one.

## Identifiers & versioning

- Canonical entities carry their own internal `canonical_id` (UUID), distinct from source-system identifiers, which are retained as `identifier` arrays (system + value + type) so round-tripping back to the source system stays possible.
- Canonical model schema itself is versioned (`schema_version` field) so future field additions don't silently break older stored instances.
- Vocabulary mappings (HL7 tables → FHIR ValueSets) are versioned configuration, not hardcoded dictionaries — several fields above require them and they change independently of code.

## Data classification & storage separation

| Store | Contents | Classification | Access |
|---|---|---|---|
| **PHI store** | Full canonical instances | PHI | RBAC + ABAC + field-level filtering; every access audited |
| **Dead-letter store** | Unprocessable raw messages | **PHI** (contains raw payloads) | Integration Administrator only; access audited |
| **Audit log** | Append-only record of every PHI access/mutation | Sensitive metadata | Auditor role; written only by the persistence layer |
| **De-identified store** | Safe Harbor output of designated entities | De-identified | Analytics/AI consumers; no re-identification path |

**Flow invariant** (corrected — 0.1.0 stated instances live in "exactly one store," which the de-identification pipeline necessarily violates): a canonical instance is written to exactly one store *by any given pipeline*. The only permitted cross-store flow is **PHI store → de-identification service → de-identified store**, which produces a *new, transformed* instance rather than copying the original. No other cross-store path exists, and there is no reverse path from de-identified back to PHI.

## Retention & deletion

Absent from 0.1.0 entirely, and it is a genuine design tension rather than an oversight:

- **Audit log** — append-only, retention per [SRS §5.4.2](SRS.md#54-audit-logging) (commonly ~6 years, unconfirmed for this client).
- **PHI** — retention period **undefined and required from the client's compliance function**; it is not derivable from the technical spec.
- **The tension:** a patient deletion or amendment request conflicts with an append-only audit log. Standard resolution is that the audit log retains the *record of access*, including the deletion event itself, while the PHI record is removed or tombstoned. The audit entry references a `canonical_id` that no longer resolves — which is correct behavior, not a dangling reference.
- **Amendment (45 CFR §164.526)** — patients may request corrections. This implies canonical entities need version history, not in-place overwrite. Flagged as an open item, since it affects the persistence schema.

Tracked as open items in [SRS §11](SRS.md#11-open-items-and-conflicts--not-silently-resolved).

## What's explicitly deferred

- Full FHIR R4 resource coverage beyond Patient/Encounter/ServiceRequest/Observation — later hardening, once vendor-specific quirks are known (per [SRS §12](SRS.md#12-constraints-and-assumptions)).
- FHIR R5-specific field differences — R5 is a target, but mappings above are written against R4 first, as the dominant deployed version.
- Local Z-segment handling — vendor-specific, deferred with the vendor-profile assumption.
- `DiagnosticReport` as a distinct resource — ORU carries report-level structure (OBR) that properly maps to DiagnosticReport wrapping child Observations. Initial scope handles Observations; the report wrapper is a near-term addition, noted so OBR-25's correct target isn't lost.

## Revision notes

Changes from 0.1.0, following review on 2026-08-24:

| # | Issue | Resolution |
|---|---|---|
| 1 | `OBX-3 → Observation.identifier` — wrong; lost `Observation.code` entirely | OBX-3 → `Observation.code`; instance identity derived from OBR-3 + OBX-4 |
| 2 | `ORC-1, ORC-5 → status` — conflated event code with state | Split; conditional logic per official HL7 ConceptMap documented |
| 3 | `OBX-5 → valueQuantity` unconditionally | Polymorphic `value[x]` driven by OBX-2 |
| 4 | `OBR-25 → Observation.status` — wrong scope | OBR-25 is report-level → `DiagnosticReport.status` |
| 5 | `EVN-2 → Encounter.period` start | Corrected to PV1-44 (admit datetime) |
| 6 | PID-18 absent; encounter identity assumed PV1-19 | Both carried; authoritative source is per-vendor configuration |
| 7 | No dead-letter entity despite DESIGN.md committing to the store | `DeadLetterMessage` defined and classified as PHI |
| 8 | "Exactly one of three stores" invariant contradicted by de-id pipeline | Flow invariant restated correctly |
| 9 | No retention/deletion model | Section added, with the append-only/deletion tension made explicit |
| 10 | Missing clinically significant fields | Added: deceased, discharge disposition, reference range, abnormal flags, performer, referring provider |
