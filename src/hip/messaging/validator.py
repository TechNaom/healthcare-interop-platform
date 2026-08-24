"""Structural + terminology validation and transform.

Maps to ``messaging.validator`` in docs/DESIGN.md section 1. In-process Python
for the current build; kept as its own module so a future C++ service can
replace it behind the same call boundary without touching callers (ADR-006 —
C++ is a future implementation pipeline, not current scope). Implemented in
Phase 8. Phase 0 placeholder.
"""
