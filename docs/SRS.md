# Software Requirements Specification

**Project:** Healthcare Interoperability Platform
**Status:** Draft — pending sign-off on open items in §11
**Version:** 0.2.0 · 2026-08-24 (supersedes 0.1.0 — restructured around client-provided detailed SRS, merged with existing ADRs)

Section numbers below double as stable requirement identifiers (e.g. `4.1.3`) — reference them in code comments, tests, and PRs once build starts.

---

## 1. Purpose and scope

This document defines functional, non-functional, security, and compliance requirements for a healthcare data integration platform that processes HL7 v2 and FHIR messages in a HIPAA-aligned manner, using **Python for API/orchestration**. C++ for high-performance/low-level components is a **documented future phase, not current build scope** — see [ADR-006](DECISIONS.md#adr-006).

The system exposes APIs and services to ingest, transform, validate, store, and exchange clinical data between EHRs, ancillary systems, and analytics/AI components, enforcing privacy and security controls aligned to HIPAA technical safeguards.

## 2. Standards and references

- **HL7 Version 2.x** messaging standard for legacy interfaces (ADT, ORM, ORU).
- **HL7 FHIR R4/R5** for RESTful APIs and modern interoperability.
- **HIPAA Security Rule** technical safeguards: access control, audit controls, integrity, person/entity authentication, transmission security (full mapping in [SECURITY_AND_COMPLIANCE.md](SECURITY_AND_COMPLIANCE.md)).
- **Python ecosystem:** `python-hl7` (or equivalent) for HL7 v2 parsing; `fhir.resources` / `fhirclient` for FHIR resource modeling and validation; FastAPI as the web framework; `structlog` (or equivalent) for structured audit-capable logging.
- **C++ ecosystem (future phase):** a FHIR-capable library such as `fhircpp`, or custom C++ models aligned to the official HL7 FHIR specification — not selected/committed until the C++ phase is scheduled.

## 3. System architecture overview

Full detail in [ARCHITECTURE.md](ARCHITECTURE.md). Summary: a layered architecture —

1. **Integration Gateway (Python)** — FastAPI-based REST layer for FHIR APIs and admin endpoints; authN/authZ, request validation, throttling, error handling.
2. **Messaging Engine (Python-only for now)** — HL7 v2 parsing, routing, transformation, and validation, all in Python. High-volume/low-latency validation in C++ is a future phase behind the same module boundary ([ADR-006](DECISIONS.md#adr-006)).
3. **Data Persistence Layer** — HIPAA-aligned store with encryption at rest for PHI; separate immutable/WORM-capable audit-log store; separate de-identified store.
4. **Security & Compliance Services** — centralized audit logging, key management, de-identification services, minimum-necessary access configuration.

## 4. Functional requirements

### 4.1 HL7 v2 message handling

1. The system shall support ingestion of HL7 v2.x messages over MLLP, file-drop, and HTTP-based APIs.
2. The system shall parse HL7 v2 messages into structured objects using a Python HL7 library.
3. The system shall validate HL7 v2 messages against configurable profiles (message types, segments, required fields).
4. The system shall support routing rules based on message type (e.g. `ADT^A01`, `ORM^O01`) and key fields (PID, PV1, ORC).
5. The system shall support transformation of HL7 v2 messages to the internal canonical model, and from there to equivalent FHIR resources (e.g. PID → `Patient`, ORC/OBR → `ServiceRequest`/`DiagnosticReport`) — see [DATA_MODEL.md](DATA_MODEL.md) for the full mapping.
6. The system shall provide ACK/NACK responses with meaningful, structured error codes for failed validations.

### 4.2 FHIR API services (Python)

1. The platform shall expose RESTful FHIR R4/R5 endpoints for core resources: Patient, Encounter, Observation, Condition, Practitioner, Organization, Medication (initial build covers Patient, Encounter, Observation, and Order-derived resources per [DATA_MODEL.md](DATA_MODEL.md); the rest extend the same pattern).
2. The system shall use a Python FHIR library to represent resources as typed models and validate payloads against the FHIR specification and any custom profiles.
3. The API shall support CRUD operations and search with common parameters (e.g. `Patient?identifier=`, `Observation?patient=`) for supported resources.
4. The system shall support versioning and ETag/If-Match semantics for concurrent update control.
5. The system shall expose SMART-on-FHIR–compatible OAuth 2.0 scopes and launch context **if required by consuming apps** — not committed for the initial build unless a consuming app needs it; see open item in §11.

### 4.3 High-performance validation/transform — future phase (not current build)

Per [ADR-006](DECISIONS.md#adr-006), this section describes the target design for a later phase; none of it is built now.

1. The solution will include C++ components for high-throughput FHIR/HL7 validation and performance-critical transformation (e.g. batch ingestion, protocol gateways, device data parsing) once that phase is scheduled.
2. C++ modules will be exposed to Python via native bindings (pybind11, in-process) or gRPC/REST microservices (out-of-process, horizontally scalable) — gRPC is the default per [ADR-002](DECISIONS.md#adr-002).
3. C++ models will align with the official HL7 FHIR specification's primitive and complex types.

### 4.4 Data storage and access

1. The system shall store PHI only in designated HIPAA-aligned database instances with encryption at rest enabled.
2. The system shall enforce role-based access control and field-level filtering to ensure minimum-necessary disclosure in API response models.
3. The platform shall maintain logical separation between the production PHI store and de-identified datasets used for analytics, testing, and AI model training — no code path bridges them without an explicit, separately-authorized re-linking service (not in initial scope).

## 5. HIPAA and security requirements

Full technical-safeguard mapping and rationale in [SECURITY_AND_COMPLIANCE.md](SECURITY_AND_COMPLIANCE.md). Summary of specific controls:

### 5.1 Access control

1. All access to PHI-handling APIs shall require strong authentication. Baseline: token-based login (OAuth 2.0/OpenID Connect). **Institutional SSO/SAML federation is an open item — see §11; the original roadmap scoped it out as needing a separate procurement conversation with a real identity provider.**
2. Authorization shall combine **RBAC** (roles: clinician, admin, integration engine, analytics service) with **ABAC** (attribute-based rules — e.g. patient-specific vs. population-level scope) where role alone is insufficient.
3. APIs shall implement "minimum necessary" by default — Python response models filter out non-required fields per endpoint/use case, not left to the caller to ignore extra fields.
4. Automatic logoff/session-expiry shall apply to any interactive session or long-lived token, minimizing exposure from an unattended session.

### 5.2 Transmission security

1. All network communication carrying PHI shall use **TLS 1.2+** with modern cipher suites, over HTTPS.
2. MLLP-based HL7 channels shall be tunneled over secure VPN or a TLS-enabled channel per enterprise security policy.
3. Keys and certificates shall be managed centrally via the `KeyManager` interface (Vault reference implementation) — never embedded in config or code.

### 5.3 Encryption and data protection

1. Databases/storage containing PHI shall use **encryption at rest** — reference: AES-256 disk encryption — with keys managed through `KeyManager`.
2. Sensitive fields may additionally be encrypted at the application layer for defense in depth on especially high-risk PHI elements.
3. Backups shall be encrypted and stored in compliant locations with a documented retention policy.

### 5.4 Audit logging

1. The system shall generate structured audit logs for all PHI operations, capturing: user/service identity, patient/resource identifiers, operation (create/read/update/delete/search), timestamp, and source IP/host.
2. Audit logs shall be written to an immutable/WORM-capable store (e.g. object-lock storage, append-only DB) with retention aligned to regulatory expectations (commonly 6 years — confirm exact figure with the client's compliance function, not assumed here).
3. Logging shall be standardized across the codebase (structured logging library), so every component forwards events to the same sink in the same shape.
4. **AI-assisted anomaly detection over audit logs** is a requested capability. Treated as a **future/optional enhancement**, not initial build scope: if it uses a third-party service, it needs a signed BAA first like any other third-party touching audit metadata ([SECURITY_AND_COMPLIANCE.md §5](SECURITY_AND_COMPLIANCE.md)); a self-hosted anomaly-detection component would not need one. Which approach is wanted is an open item — see §11.

### 5.5 Integrity and validation

1. All HL7 v2 and FHIR messages shall be schema-validated before persistence or downstream processing.
2. The system shall implement checksum/hash-based integrity verification for stored documents or large payloads where appropriate.
3. Validation errors shall be logged and surfaced through monitoring/alerting, not just swallowed into the dead-letter store silently.

## 6. Privacy and de-identification

1. The system shall provide configurable de-identification pipelines for:
   - **Structured data** — Safe Harbor rules (date shifting, geocode generalization, age capping at 89, and the remaining categories in [SECURITY_AND_COMPLIANCE.md §4](SECURITY_AND_COMPLIANCE.md#4-de-identification)). **Initial build scope.**
   - **Unstructured text** — NER-based de-identification (Presidio-like approach). **Deferred**, per the original roadmap — its own future phase, not initial scope.
2. De-identified datasets shall be clearly separated from identified PHI stores (see [DATA_MODEL.md](DATA_MODEL.md#data-classification--storage-separation)); any re-identification keys, if ever used, are protected and access-controlled — no re-identification path exists in the initial build.
3. De-identification configuration shall be versioned and auditable for research/analytics use.

## 7. Non-functional requirements

### 7.1 Performance and scalability

1. The system shall support a defined message throughput and latency target under normal load. Default assumption: ~50 HL7 msg/s, ~200 FHIR req/s, P95 < 300ms (see §11) — **provisional for the Python-only build**; sized originally assuming a C++ validator, so re-benchmark against the actual Python implementation rather than assuming it holds.
2. Once/if the future C++ phase lands, those services shall be horizontally scalable for CPU-intensive operations, with the Python orchestration layer handling backpressure and rate limiting.
3. Multi-tenant deployment (logical segregation) is supported **if required** — not committed for the initial build; add if a concrete tenant-isolation need shows up.

### 7.2 Reliability and availability

1. Target availability SLA for core FHIR APIs and HL7 channels: to be set with the client (no figure assumed here — an SLA number implies an operational commitment this document shouldn't invent).
2. Redundancy with automatic failover for critical services/databases — a later-phase concern per the roadmap's "multi-region/HA" exclusion; noted here so it isn't lost, not committed for the pilot.
3. A message queue/event stream (Kafka or RabbitMQ, via the `MessageBus` interface) decouples producers/consumers only where a phase actually needs that decoupling — not introduced speculatively.

### 7.3 Observability

1. Centralized logging, metrics, and tracing (OpenTelemetry) across all components.
2. Health/readiness endpoints for orchestration-platform liveness/readiness probes.
3. Security and validation failures integrate with a SIEM **if the client has one** — self-hosted/internal by default per [NFR-6](#nonfunctional-hard-constraints); no data leaves to a third-party SIEM without a BAA.

## 8. Technology stack requirements

### 8.1 Python (current build)

- Web framework: **FastAPI**.
- FHIR: `fhir.resources` and/or `fhirclient`.
- HL7 v2: `python-hl7` or equivalent.
- Auth: OAuth 2.0/OpenID Connect client/server libraries.
- Logging: `structlog` or equivalent, standardized across all modules.

### 8.2 C++ (future phase — not current build)

- FHIR modeling: `fhircpp` or code generated from the official HL7 FHIR specification — evaluated when the phase is actually scheduled, not committed now.
- gRPC/REST framework for inter-service communication with the Python layer.
- CMake-based builds, containerized identically to the Python services.

## 9. Compliance, documentation, and governance

1. A data-flow diagram of all PHI ingress, storage, processing, and egress paths shall be maintained and updated as part of the design baseline (living document — update alongside [ARCHITECTURE.md](ARCHITECTURE.md), not a one-time deliverable).
2. System documentation shall include interface specifications (HL7 v2 + FHIR endpoints), security/privacy design including threat models, and operational runbooks for incident response and breach handling — the runbook is explicitly deferred in the roadmap until the system it describes is stable.
3. A requirements traceability matrix (HIPAA requirements → technical controls; HL7/FHIR conformance → implemented functionality) is valuable but, per the roadmap, written once the system is stable rather than maintained speculatively during active early-phase churn.

## 10. Implementation and testing requirements

1. **Unit tests** — HL7 v2/FHIR parsing and validation; field-level enforcement of minimum-necessary views in API responses.
2. **Integration tests** — end-to-end (HL7 v2 ingest → transform → FHIR API exposure → persistence); authN/authZ flows including negative cases.
3. **Security/compliance testing** — static and dynamic code analysis in CI; third-party penetration testing and audit-log completeness/retention audits are vendor-scheduled and explicitly out of scope for the initial build per the roadmap (shouldn't touch real PHI without a BAA regardless).
4. All test fixtures are synthetic, no exceptions — [ADR-005](DECISIONS.md#adr-005).

## 11. Open items and conflicts — not silently resolved

| # | Item | Why it's open |
|---|---|---|
| 1 | **SSO/SAML institutional federation** (§5.1) | This SRS requires it; the original roadmap explicitly scoped full OAuth2/OIDC+SAML SSO federation **out** of the initial build as needing a separate procurement conversation with a real IdP. Baseline OAuth2/OIDC token auth is in scope either way — the open question is whether full SAML federation is needed for the pilot or deferred as originally planned. |
| 2 | **AI-assisted audit-log anomaly detection** (§5.4) | Requested capability, not yet scoped as self-hosted vs. third-party. Third-party requires a BAA first. |
| 3 | **Build track** | 8-week vs. 12-week AI-orchestrated timeline — default assumed 12-week, unconfirmed. |
| 4 | **Availability SLA figure** (§7.2) | No number invented here; needs a client-side commitment. |
| 5 | **Audit-log retention period** (§5.4.2) | "6 years" used as a common reference point, not confirmed against the client's actual regulatory obligation. |

## 12. Constraints and assumptions

| Assumption | Default | Status |
|---|---|---|
| Deployment target | Container-first, any Kubernetes distro or Compose on-prem | Assumed |
| EHR vendors | Generic HL7 v2.x + FHIR R4, no vendor-specific profiles yet | Assumed |
| Throughput | ~50 msg/s HL7, ~200 req/s FHIR, P95 < 300ms | Assumed, provisional (see §7.1) |
| Team size | 1–2 senior engineers + part-time security review | Assumed |
| Implementation language | **Python-only for current build; C++ is a future implementation pipeline** | **Confirmed 2026-08-24 — [ADR-006](DECISIONS.md#adr-006)** |
| PHI in dev/test | Synthetic data only, no exceptions | Hard rule, non-negotiable |
