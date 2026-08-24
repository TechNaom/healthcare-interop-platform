"""FHIR R4/R5 REST routes and resource (de)serialization.

Maps to ``gateway.api.fhir`` in docs/DESIGN.md section 1. Routes target the
canonical model (ADR-001), never HL7 directly. Implemented in Phase 6-7; the
FastAPI router wiring lands then. Phase 0 is a placeholder so the package
imports cleanly.
"""
