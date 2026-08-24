"""KeyManager interface + Vault reference implementation.

Maps to ``security.keymanager`` in docs/DESIGN.md section 1/5. Backs
encryption-key operations; the default implementation is self-hosted
HashiCorp Vault, never a cloud KMS (ADR-003, docs/TECH_STACK.md). Implemented in
Phase 9. Phase 0 placeholder.
"""
