"""Data Persistence Layer.

Three separate stores (docs/DESIGN.md section 1, docs/ARCHITECTURE.md):
``phi_repo`` (encrypted PHI, RBAC + field-level filtering), ``audit_log``
(append-only — no update/delete code path exists), and ``deid_repo``
(de-identified store, kept separate for analytics). Access goes through
SQLAlchemy 2.x async repositories so business logic never holds a connection.
Interface stubs only at Phase 0.
"""
