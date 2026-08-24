"""De-identified store reads/writes.

Maps to ``persistence.deid_repo`` in docs/DESIGN.md section 1. Kept physically
separate from the PHI store; holds Safe-Harbor-de-identified records for
analytics/AI. Populated by ``hip.security.deid``. Implemented in Phase 10.
Phase 0 placeholder.
"""
