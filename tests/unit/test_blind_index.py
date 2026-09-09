"""Unit tests for the blind index (searchable HMAC of identifiers)."""

from __future__ import annotations

import os
from unittest import mock

import pytest

from hip.security.blind_index import BlindIndexer, HmacBlindIndexer, blind_indexer_from_env

pytestmark = pytest.mark.unit


def test_deterministic_and_matches_same_value() -> None:
    idx = HmacBlindIndexer(b"key")
    assert idx.index("MRN1") == idx.index("MRN1")


def test_trims_whitespace_but_keeps_case() -> None:
    idx = HmacBlindIndexer(b"key")
    assert idx.index("  MRN1 ") == idx.index("MRN1")
    assert idx.index("mrn1") != idx.index("MRN1")  # case-sensitive


def test_different_keys_differ_and_value_not_recoverable() -> None:
    a, b = HmacBlindIndexer(b"key-a"), HmacBlindIndexer(b"key-b")
    digest = a.index("MRN1")
    assert digest != b.index("MRN1")
    assert "MRN1" not in digest  # digest reveals nothing of the plaintext


def test_satisfies_protocol() -> None:
    assert isinstance(HmacBlindIndexer(b"k"), BlindIndexer)


def test_from_env() -> None:
    with mock.patch.dict(os.environ, {"HIP_BLIND_INDEX_KEY": "secret"}):
        assert blind_indexer_from_env() is not None
    with mock.patch.dict(os.environ, {}, clear=True):
        assert blind_indexer_from_env() is None
