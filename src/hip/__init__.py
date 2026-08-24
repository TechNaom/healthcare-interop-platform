"""Healthcare Interoperability Platform (hip).

HIPAA-aligned HL7 v2 + FHIR (R4/R5) integration engine. Python-only for the
current build (ADR-006). Package root for every layer described in
docs/DESIGN.md section 1:

    hip.gateway      Integration Gateway (FastAPI): FHIR/admin APIs, auth, rate limiting
    hip.messaging    Messaging Engine: HL7 ingestion, canonical mapping, validation
    hip.persistence  PHI store, append-only audit log, de-identified store
    hip.security     KeyManager / SecretsProvider / ObjectStore / de-identification
    hip.platform     OS-agnostic shim (renamed from the roadmap's ``platform/`` to
                     avoid shadowing the stdlib ``platform`` module)

Phase 0 status: interface stubs only. No business logic yet.
"""

__version__ = "0.0.0"
