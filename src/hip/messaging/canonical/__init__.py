"""Canonical model mapping — the heart of the system (ADR-001).

Everything maps to/from one internal canonical model; there are no direct
HL7<->FHIR translators. The field-level mappings live in docs/DATA_MODEL.md and
must be reviewed before code is written against them.
"""
