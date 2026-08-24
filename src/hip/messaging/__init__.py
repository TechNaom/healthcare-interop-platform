"""Messaging Engine (Python-only for the current build — ADR-006).

Ingests HL7 v2 (MLLP/HTTP/file-drop), parses and routes it, maps to/from the
one canonical model (ADR-001), and validates/transforms. The validation step is
kept in its own module (``hip.messaging.validator``) so a future C++ service can
replace it behind the same call boundary without touching callers. Interface
stubs only at Phase 0.
"""
