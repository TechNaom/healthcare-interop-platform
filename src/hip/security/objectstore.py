"""ObjectStore interface + MinIO / local-FS reference implementation.

Maps to ``security.objectstore`` in docs/DESIGN.md section 1/5. S3-compatible
blob storage backed by self-hosted MinIO (or local FS in dev), used when a phase
needs blobs. No cloud object storage (ADR-003). Implemented when first needed.
Phase 0 placeholder.
"""
