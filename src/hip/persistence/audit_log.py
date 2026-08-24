"""Append-only audit log writes.

Maps to ``persistence.audit_log`` in docs/DESIGN.md section 1. Satisfies HIPAA
audit controls (SRS section 5.4, security §164.312(b)). **No update or delete
code path exists by design** — the store is immutable and append-only. The
schema must stay queryable enough to support the later self-hosted anomaly
detection (ADR-009), even though that analysis component is out of initial
scope. Implemented in Phase 9. Phase 0 placeholder.
"""
