"""Vault secret retrieval (ADR-003 — Vault is the production key/secret source,
never a cloud KMS).

A minimal KV-v2 read used by ``keymanager_from_env`` / ``blind_indexer_from_env``
to source their key material in production, while local dev/tests keep using a
plain env var. Vault being *configured but unreachable* is a hard failure
(``VaultError``) rather than a silent "not configured" — that distinction
matters because "not configured" fails closed per-request (refuse to touch
PHI), whereas a broken Vault a caller expected to reach should surface loudly.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class VaultError(Exception):
    """Vault is configured (``HIP_VAULT_ADDR`` set) but the secret could not
    be read — wrong token, unreachable server, missing field, etc."""


def read_secret(path: str, field: str) -> str | None:
    """Read ``field`` from the KV-v2 secret at ``path`` (e.g.
    ``secret/data/hip/encryption-key``). Returns ``None`` if Vault isn't
    configured at all (``HIP_VAULT_ADDR`` unset) so callers can fall back to a
    plain env var for local dev.
    """
    addr = os.environ.get("HIP_VAULT_ADDR")
    if not addr:
        return None
    token = os.environ.get("HIP_VAULT_TOKEN")
    if not token:
        raise VaultError("HIP_VAULT_ADDR is set but HIP_VAULT_TOKEN is not")

    url = f"{addr.rstrip('/')}/v1/{path.lstrip('/')}"
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise VaultError(f"HIP_VAULT_ADDR must be http(s), got: {addr!r}")
    request = urllib.request.Request(url, headers={"X-Vault-Token": token})  # noqa: S310 - scheme validated above
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - scheme validated above  # nosec B310
            body = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise VaultError(f"could not reach Vault at {addr}: {exc}") from exc

    try:
        value = body["data"]["data"][field]
    except (KeyError, TypeError) as exc:
        raise VaultError(f"Vault secret {path!r} has no field {field!r}") from exc
    if not isinstance(value, str):
        raise VaultError(f"Vault secret {path!r} field {field!r} is not a string")
    return value
