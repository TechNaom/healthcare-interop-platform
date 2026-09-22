"""Unit tests for Vault secret retrieval (ADR-003 production key source)."""

from __future__ import annotations

import json
import os
import urllib.error
from collections.abc import Mapping
from unittest import mock

import pytest

from hip.security.vault import VaultError, read_secret

pytestmark = pytest.mark.unit


def _fake_response(body: Mapping[str, object]) -> mock.MagicMock:
    response = mock.MagicMock()
    response.read.return_value = json.dumps(body).encode()
    response.__enter__.return_value = response
    return response


def test_none_when_vault_not_configured() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        assert read_secret("secret/data/hip/encryption-key", "key") is None


def test_configured_without_token_raises() -> None:
    with mock.patch.dict(os.environ, {"HIP_VAULT_ADDR": "http://vault:8200"}, clear=True):
        with pytest.raises(VaultError, match="HIP_VAULT_TOKEN"):
            read_secret("secret/data/hip/encryption-key", "key")


def test_reads_field_from_kv2_response() -> None:
    body = {"data": {"data": {"key": "the-secret-value"}}}
    env = {"HIP_VAULT_ADDR": "http://vault:8200", "HIP_VAULT_TOKEN": "tok"}
    with (
        mock.patch.dict(os.environ, env, clear=True),
        mock.patch("urllib.request.urlopen", return_value=_fake_response(body)) as urlopen,
    ):
        value = read_secret("secret/data/hip/encryption-key", "key")
    assert value == "the-secret-value"
    request = urlopen.call_args[0][0]
    assert request.full_url == "http://vault:8200/v1/secret/data/hip/encryption-key"
    assert request.headers["X-vault-token"] == "tok"


def test_unreachable_vault_raises() -> None:
    env = {"HIP_VAULT_ADDR": "http://vault:8200", "HIP_VAULT_TOKEN": "tok"}
    with (
        mock.patch.dict(os.environ, env, clear=True),
        mock.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ),
    ):
        with pytest.raises(VaultError, match="could not reach Vault"):
            read_secret("secret/data/hip/encryption-key", "key")


def test_missing_field_raises() -> None:
    body = {"data": {"data": {"other": "x"}}}
    env = {"HIP_VAULT_ADDR": "http://vault:8200", "HIP_VAULT_TOKEN": "tok"}
    with (
        mock.patch.dict(os.environ, env, clear=True),
        mock.patch("urllib.request.urlopen", return_value=_fake_response(body)),
    ):
        with pytest.raises(VaultError, match="no field"):
            read_secret("secret/data/hip/encryption-key", "key")
