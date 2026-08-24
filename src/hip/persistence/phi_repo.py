"""PHI store reads/writes with field-level filtering by role.

Maps to ``persistence.phi_repo`` in docs/DESIGN.md section 1. Encrypted at rest;
RBAC filtering is applied here, but the authorization *decision* is the
Gateway's (``hip.gateway.auth``). Every read/write emits an audit event via
``hip.persistence.audit_log``. Implemented in Phase 9. Phase 0 placeholder.
"""
