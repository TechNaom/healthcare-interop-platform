# Glossary

| Term | Meaning |
|---|---|
| **HL7 v2** | Health Level Seven Version 2 — the dominant legacy messaging standard between healthcare systems (ADT, ORM, ORU, etc.), pipe-and-hat delimited text segments. |
| **FHIR** | Fast Healthcare Interoperability Resources — modern HL7 standard, resource-oriented, REST/JSON-based. R4 and R5 are versions. |
| **ADT** | Admit/Discharge/Transfer — HL7 v2 message type carrying patient demographic and encounter events. |
| **ORM** | Order message — HL7 v2 message type carrying orders (labs, meds, procedures). |
| **ORU** | Observation Result — HL7 v2 message type carrying results (e.g., lab values). |
| **MLLP** | Minimal Lower Layer Protocol — the standard TCP transport wrapper for HL7 v2 messages. |
| **PHI** | Protected Health Information — individually identifiable health information covered by HIPAA. |
| **BAA** | Business Associate Agreement — the legal contract required before a third party may touch PHI. |
| **Safe Harbor** | A HIPAA de-identification method (45 CFR §164.514(b)(2)) — removes 18 specified identifier categories. |
| **RBAC** | Role-Based Access Control — authorization model where permissions attach to roles, not individual users. |
| **Canonical data model** | This project's single internal representation that both HL7 v2 and FHIR map to/from, avoiding pairwise translators. See [ADR-001](DECISIONS.md#adr-001). |
| **gRPC** | Google's RPC framework — used here as the default Python↔C++ service boundary. |
| **pybind11** | A C++/Python binding library — used here only as a fallback for in-process calls where gRPC latency is measured unacceptable. |
| **OCI image** | Open Container Initiative image format — the standard container image format (what Docker builds). |
| **OpenTelemetry** | Vendor-neutral observability standard for traces, metrics, and logs. |
| **KeyManager / SecretsProvider / ObjectStore** | This project's pluggable infrastructure interfaces — see [DESIGN.md §5](DESIGN.md#5-pluggable-infrastructure--interface-shapes). |
| **De-identified store** | A separate data store holding Safe Harbor de-identified copies of records, used for analytics/AI with no path back to PHI. |
| **RBAC** | Role-Based Access Control — permissions attach to roles, not individual users. |
| **ABAC** | Attribute-Based Access Control — permissions evaluated from attributes of the request (e.g. "this clinician, this patient population"), used alongside RBAC where role alone can't express the rule. |
| **WORM** | Write Once, Read Many — storage that can't be modified or deleted after write; used for the audit log. |
| **KMS** | Key Management System — centralized management of encryption keys and certificates; this project's `KeyManager` interface, Vault by default. |
| **SIEM** | Security Information and Event Management — a system that aggregates and analyzes security event data; self-hosted/internal by default here, no third-party SIEM without a BAA. |
| **SMART on FHIR** | A standard for OAuth 2.0-based app authorization launched in a FHIR context (scopes, launch context) — relevant only if a consuming app requires app-launch semantics beyond baseline API auth. |
| **Keycloak** | Open-source, self-hostable identity and access management server — this project's identity provider, speaking both OIDC and SAML ([ADR-008](DECISIONS.md#adr-008)). |
| **ConceptMap** | A FHIR resource defining how codes in one system translate to another; HL7 publishes official v2-to-FHIR ConceptMaps that this project's canonical mappings follow. |
| **Dead-letter store** | Where messages that fail parsing, validation, or transformation are retained for diagnosis. Contains raw HL7 payloads, therefore classified as a **PHI store**, not a debug log. |

