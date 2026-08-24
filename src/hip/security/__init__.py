"""Security & Compliance Services.

Pluggable infrastructure interfaces with self-hosted reference implementations
(docs/DESIGN.md section 5, ADR-003): ``keymanager`` and ``secrets`` (Vault),
``objectstore`` (MinIO / local FS), plus the ``deid`` Safe Harbor pipeline.
Business logic depends on the interfaces here, never on a vendor SDK. Interface
stubs only at Phase 0.
"""
