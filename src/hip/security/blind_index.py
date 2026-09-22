"""Blind index — searchable HMAC of identifiers without exposing PHI.

Encryption at rest makes the PHI payload unqueryable in SQL. To still support
exact-match search (e.g. find a Patient by MRN), each identifier is stored as a
keyed HMAC-SHA256 digest in a separate index. A caller's search value is hashed
the same way and matched against the index — the plaintext identifier is never
stored in the searchable column, and the digest is not reversible without the key.

The key is separate from the encryption key and, like it, comes from Vault/env in
production. Fail-closed: without a key, search is unavailable (never fall back to
scanning decrypted PHI).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Protocol, runtime_checkable

from hip.security import vault


@runtime_checkable
class BlindIndexer(Protocol):
    def index(self, value: str) -> str: ...


class HmacBlindIndexer:
    """Keyed HMAC-SHA256 blind index. Values are trimmed before hashing so
    incidental whitespace doesn't defeat exact match; case is preserved
    (identifiers are case-sensitive)."""

    def __init__(self, key: bytes) -> None:
        self._key = key

    def index(self, value: str) -> str:
        return hmac.new(self._key, value.strip().encode(), hashlib.sha256).hexdigest()


def blind_indexer_from_env() -> BlindIndexer | None:
    """Build a blind indexer, preferring Vault (production, ADR-003) over the
    ``HIP_BLIND_INDEX_KEY`` env var (local dev/tests), or None (search off)."""
    path = os.environ.get("HIP_VAULT_BLIND_INDEX_KEY_PATH", "secret/data/hip/blind-index-key")
    key = vault.read_secret(path, "key") or os.environ.get("HIP_BLIND_INDEX_KEY")
    return HmacBlindIndexer(key.encode()) if key else None
