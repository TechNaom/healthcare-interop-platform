# Software Requirements Specification

**Project:** Healthcare Interoperability Platform
**Status:** Draft — pending sign-off on assumptions in §9
**Version:** 0.1.0 · 2026-08-24

Requirement IDs are stable identifiers — reference them in code comments, tests, and PRs once build starts, so a requirement traces to the commit(s) that satisfy it.

---

## 1. Purpose & scope

This platform ingests HL7 v2 messages and serves/accepts FHIR R4/R5 resources for a healthcare organization, transforming between the two through one internal canonical data model, while meeting HIPAA technical-safeguard expectations for anything touching Protected Health Information (PHI).

**In scope:** HL7 v2 ingestion (ADT, ORM, ORU), FHIR R4/R5 REST API, canonical transformation, PHI/audit/de-identified persistence, RBAC, encryption, Safe Harbor de-identification, containerized deployment.

**Out of scope for the initial build** (see [ROADMAP §Out of scope](<../Healthcare Interop Platform.md#out-of-scope-for-either-track--and-why-more-weeks-wouldnt-fix-it>) for rationale): SSO/SAML federation, third-party pen-testing, NLP-based de-identification, multi-region HA, formal traceability matrix.

## 2. Definitions

See [GLOSSARY.md](GLOSSARY.md) for all acronyms (HL7, FHIR, PHI, BAA, RBAC, etc.).

## 3. System overview

Four layers — Integration Gateway, Messaging Engine, Persistence, Security & Compliance Services — detailed in [ARCHITECTURE.md](ARCHITECTURE.md). HL7 v2 and FHIR both map to and from one canonical model rather than being translated pairwise (see [ADR-001](DECISIONS.md#adr-001)).

## 4. Actors

| Actor | Description |
|---|---|
| **Sending EHR / HL7 source system** | Pushes HL7 v2 messages via MLLP, HTTP, or file-drop |
| **FHIR client** | Consumes or writes FHIR resources via the REST API (clinical app, analytics tool, another integration engine) |
| **Integration Administrator** | Configures routing, credentials, and monitors message flow |
| **Auditor / Compliance Officer** | Reads audit logs, verifies access-control and de-identification behavior; never touches raw PHI beyond what their role permits |
| **Analytics / AI consumer** | Reads only from the de-identified store, never the PHI store |

## 5. Functional requirements

### 5.1 HL7 v2 ingestion

| ID | Requirement |
|---|---|
| FR-1.1 | The system **shall** accept HL7 v2.x messages over MLLP, HTTP, and file-drop transports. |
| FR-1.2 | The system **shall** parse ADT, ORM, and ORU message types in the initial release. |
| FR-1.3 | The system **shall** validate incoming messages against HL7 v2 structural rules before transformation. |
| FR-1.4 | The system **shall** return an ACK for successfully processed messages and a NACK with a structured reason code for rejected ones. |
| FR-1.5 | The system **shall** route messages to configured downstream targets based on message type and configurable rules. |
| FR-1.6 | Malformed messages **shall** be persisted to a dead-letter store rather than silently dropped. |

### 5.2 Canonical transformation

| ID | Requirement |
|---|---|
| FR-2.1 | The system **shall** transform validated HL7 v2 messages into the canonical data model (see [DATA_MODEL.md](DATA_MODEL.md)). |
| FR-2.2 | The system **shall** transform canonical model instances into FHIR R4 resources on read, and FHIR R4 resources into canonical model instances on write. |
| FR-2.3 | Transformation failures **shall** be logged with enough detail (source message ID, failing field, rule) to be diagnosed without re-requesting the source message. |

### 5.3 FHIR API

| ID | Requirement |
|---|---|
| FR-3.1 | The system **shall** expose FHIR R4 RESTful CRUD endpoints for Patient, Encounter, Observation, and Order-derived resources (ServiceRequest/MedicationRequest as applicable) in the initial release. |
| FR-3.2 | The system **shall** support FHIR search parameters relevant to each exposed resource type. |
| FR-3.3 | The system **shall** reject writes that fail FHIR resource validation, returning an `OperationOutcome`. |
| FR-3.4 | Admin endpoints (routing config, health, metrics) **shall** be separated from clinical data endpoints, both in path namespace and in required authorization scope. |

### 5.4 Persistence

| ID | Requirement |
|---|---|
| FR-4.1 | PHI **shall** be stored encrypted at rest, in a store logically and physically separate from the de-identified store. |
| FR-4.2 | Every read or write of PHI **shall** produce an immutable audit log entry (actor, action, resource, timestamp, outcome). |
| FR-4.3 | The audit log store **shall** be append-only; no code path may update or delete an existing audit entry. |
| FR-4.4 | Field-level access control **shall** be enforceable per role (e.g., an Auditor role can see audit metadata but not clinical note text). |

### 5.5 De-identification

| ID | Requirement |
|---|---|
| FR-5.1 | The system **shall** provide a pipeline that produces Safe Harbor de-identified copies of designated resources into the de-identified store. |
| FR-5.2 | De-identification **shall** strip or generalize all 18 Safe Harbor identifier categories (see [SECURITY_AND_COMPLIANCE.md](SECURITY_AND_COMPLIANCE.md#de-identification)). |
| FR-5.3 | The de-identified store **shall** have no code path back to re-identification without a separate, explicitly authorized re-linking service (not in initial scope). |

### 5.6 Security & identity

| ID | Requirement |
|---|---|
| FR-6.1 | All API access **shall** require authentication; there is no anonymous access path to clinical endpoints. |
| FR-6.2 | Authorization **shall** be role-based, enforced centrally rather than per-endpoint ad hoc. |
| FR-6.3 | Secrets (DB credentials, signing keys, API keys) **shall** be retrieved through a `SecretsProvider` interface, never hardcoded or committed. |
| FR-6.4 | Rate limiting **shall** apply per client/API-key on the Integration Gateway. |

### 5.7 Observability

| ID | Requirement |
|---|---|
| FR-7.1 | The system **shall** emit structured logs and OpenTelemetry traces for every message/request processed. |
| FR-7.2 | Logs and traces **shall not** contain raw PHI field values; only resource identifiers and outcome metadata. |
| FR-7.3 | The system **shall** expose health and readiness endpoints suitable for container-orchestrator probes. |

## 6. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | Sustain ≥ 50 HL7 msg/s and ≥ 200 FHIR req/s at the assumed default throughput target (§9), horizontally scalable beyond that via added C++ service instances. |
| NFR-2 | FHIR API P95 latency < 300ms under target load. |
| NFR-3 | No OS-specific code path anywhere in the codebase; C++ platform code isolated behind a single `platform/` shim. |
| NFR-4 | Every service ships as a multi-arch (`linux/amd64`, `linux/arm64`) container image, buildable and runnable identically under Compose or any Kubernetes distribution. |
| NFR-5 | No hardcoded cloud-vendor SDK in core business logic; infrastructure dependencies (`KeyManager`, `ObjectStore`, `MessageBus`, DB) sit behind swappable interfaces. |
| NFR-6 | No telemetry, error reporting, or log sink targets third-party SaaS unless a signed BAA exists and it is explicitly configured — off by default. |
| NFR-7 | Zero real PHI in source control, test fixtures, CI logs, or this repository at any point (see [ADR-005](DECISIONS.md#adr-005)). |

## 7. External interfaces

- **HL7 v2 inbound:** MLLP (default port TBD in Phase 0), HTTP POST, file-drop directory watch.
- **FHIR REST API:** `/fhir/r4/...` per resource, standard FHIR interactions (`read`, `search`, `create`, `update`).
- **Admin API:** `/admin/...`, separate auth scope from `/fhir/...`.
- **Metrics/health:** `/healthz`, `/readyz`, `/metrics` (OpenTelemetry/Prometheus-compatible).

## 8. Data requirements

See [DATA_MODEL.md](DATA_MODEL.md) for canonical entities and the HL7 v2 ↔ canonical ↔ FHIR field mapping.

## 9. Constraints & assumptions

Carried from the source SRS's open-decisions table — defaults assumed so planning isn't blocked, explicitly flagged for override:

| Assumption | Default | Status |
|---|---|---|
| Deployment target | Container-first, any Kubernetes distro or Compose on-prem | Assumed |
| EHR vendors | Generic HL7 v2.x + FHIR R4, no vendor-specific profiles yet | Assumed |
| Throughput | ~50 msg/s HL7, ~200 req/s FHIR, P95 < 300ms | Assumed |
| Team size | 1–2 senior engineers + part-time security review | Assumed |
| **Build track** | **12-week AI-orchestrated track** (see roadmap) | **Assumed, pending your confirmation** |
| **PHI in dev/test** | **Synthetic data only, no exceptions** | **Assumed as a hard rule regardless of confirmation** |

## 10. Acceptance criteria (by phase)

High-level; detailed per-phase acceptance criteria will be written at the start of each phase against the code that phase actually produces, not speculatively now. Phase 0 acceptance = repo scaffold + canonical model reviewed and signed off by you. Later phases build on that pattern: each phase ends with a demo-able increment plus tests proving the requirements it claims to satisfy.
