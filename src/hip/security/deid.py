"""Safe Harbor de-identification pipeline.

Maps to ``security.deid`` in docs/DESIGN.md section 1. Strips the HIPAA Safe
Harbor identifiers from canonical records before they land in the de-identified
store (``hip.persistence.deid_repo``). Structured-data Safe Harbor rules are in
scope; NER-based unstructured-text de-id is a documented future phase (roadmap
"out of scope"). Implemented in Phase 10. Phase 0 placeholder.
"""
