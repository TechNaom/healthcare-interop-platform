"""HL7 v2 <-> canonical <-> FHIR mapping.

Maps to ``messaging.canonical.mapper`` in docs/DESIGN.md section 1. Implements
the field-level mappings defined in docs/DATA_MODEL.md for the canonical
entities (Patient, Encounter, Observation, Order). This is the single
highest-leverage module (ADR-001) — **do not write code here until the
canonical model spec is reviewed and signed off** (see PROJECT_STATE.md "Next
recommended task"). Implemented in Phase 6. Phase 0 placeholder.
"""
