"""SecretsProvider interface + Vault reference implementation.

Maps to ``security.secrets`` in docs/DESIGN.md section 1/5. Supplies runtime
secrets (DB credentials, tokens) from self-hosted Vault. Production secrets come
from here, never from a committed ``.env`` file. Implemented in Phase 9.
Phase 0 placeholder.
"""
