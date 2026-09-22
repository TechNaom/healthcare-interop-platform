"""Unit tests for the KeyManager (encryption at rest, HIPAA 164.312(a)(2)(iv))."""

from __future__ import annotations

import os
from unittest import mock

import pytest

from hip.security.keymanager import FernetKeyManager, KeyManager, keymanager_from_env

pytestmark = pytest.mark.unit


def test_encrypt_decrypt_round_trip() -> None:
    km = FernetKeyManager(FernetKeyManager.generate_key())
    plaintext = b'{"family": "DOE"}'
    ciphertext = km.encrypt(plaintext)
    assert ciphertext != plaintext
    assert b"DOE" not in ciphertext  # plaintext not recoverable from bytes
    assert km.decrypt(ciphertext) == plaintext


def test_wrong_key_cannot_decrypt() -> None:
    a = FernetKeyManager(FernetKeyManager.generate_key())
    b = FernetKeyManager(FernetKeyManager.generate_key())
    token = a.encrypt(b"secret")
    with pytest.raises(Exception):  # noqa: B017 - cryptography.fernet.InvalidToken
        b.decrypt(token)


def test_satisfies_key_manager_protocol() -> None:
    assert isinstance(FernetKeyManager(FernetKeyManager.generate_key()), KeyManager)


def test_from_env_returns_manager_when_key_set() -> None:
    key = FernetKeyManager.generate_key()
    with mock.patch.dict(os.environ, {"HIP_ENCRYPTION_KEY": key}):
        km = keymanager_from_env()
    assert km is not None
    assert km.decrypt(km.encrypt(b"x")) == b"x"


def test_from_env_none_when_unset_fails_closed() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        assert keymanager_from_env() is None


def test_from_env_prefers_vault_over_static_env_key() -> None:
    vault_key = FernetKeyManager.generate_key()
    env_key = FernetKeyManager.generate_key()
    env = {
        "HIP_VAULT_ADDR": "http://vault:8200",
        "HIP_VAULT_TOKEN": "tok",
        "HIP_ENCRYPTION_KEY": env_key,
    }
    with (
        mock.patch.dict(os.environ, env, clear=True),
        mock.patch("hip.security.keymanager.vault.read_secret", return_value=vault_key),
    ):
        km = keymanager_from_env()
    assert km is not None
    # decrypts a value encrypted with the Vault key, not the env-var key
    ciphertext = FernetKeyManager(vault_key).encrypt(b"x")
    assert km.decrypt(ciphertext) == b"x"
