"""HL7 v2 structural parse and segment extraction.

Maps to ``messaging.hl7.parser`` in docs/DESIGN.md section 1. Uses ``python-hl7``
for structural parsing; hands parsed segments to the router and, on structural
failure, produces a NACK reason. Never maps straight to FHIR — output feeds the
canonical mapper (ADR-001). Implemented in Phase 4-5. Phase 0 placeholder.
"""
