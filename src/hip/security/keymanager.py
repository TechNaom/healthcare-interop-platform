"""KeyManager — encryption key operations (HIPAA 164.312(a)(2)(iv)).

Maps to ``security.keymanager`` in docs/DESIGN.md 1/5. An interface plus a
self-hosted reference implementation; the production key source is Vault
(ADR-003, never a cloud KMS), a thin swap behind this same interface. PHI is
encrypted at the repository boundary using a KeyManager, so at-rest ciphertext
is what Postgres ever sees.

Fail-closed: if no key is configured, ``keymanager_from_env`` returns ``None``
and any PHI write/read that needs one refuses — PHI is never stored in the clear
by omission. If Vault *is* configured but unreachable, that's a startup error
(``vault.VaultError``), not a silent fall-through to "unconfigured".
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from cryptography.fernet import Fernet

from hip.security import vault


@runtime_checkable
class KeyManager(Protocol):
    """Symmetric authenticated encryption over opaque bytes."""

    def encrypt(self, plaintext: bytes) -> bytes: ...

    def decrypt(self, ciphertext: bytes) -> bytes: ...


class FernetKeyManager:
    """Reference KeyManager using Fernet (AES-128-CBC + HMAC-SHA256, per-message
    IV). The key is supplied by config now and by Vault in production."""

    def __init__(self, key: bytes | str) -> None:
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._fernet.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self._fernet.decrypt(ciphertext)

    @staticmethod
    def generate_key() -> str:
        """A fresh Fernet key (base64). Use for local dev / tests only."""
        return Fernet.generate_key().decode()


def keymanager_from_env() -> KeyManager | None:
    """Build a KeyManager, preferring Vault (production, ADR-003) over the
    ``HIP_ENCRYPTION_KEY`` env var (local dev/tests). Returns None if neither
    is configured.

    None means "not configured" — callers must fail closed rather than fall back
    to storing PHI unencrypted.
    """
    path = os.environ.get("HIP_VAULT_ENCRYPTION_KEY_PATH", "secret/data/hip/encryption-key")
    key = vault.read_secret(path, "key") or os.environ.get("HIP_ENCRYPTION_KEY")
    return FernetKeyManager(key) if key else None
