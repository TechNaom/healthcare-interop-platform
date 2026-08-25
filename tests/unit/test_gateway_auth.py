"""Unit tests for token validation and RBAC (ADR-008, SRS 5.1)."""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from hip.gateway.auth import AuthError, TokenAuthenticator

pytestmark = pytest.mark.unit

_SECRET = "unit-test-secret-padding-to-32-bytes-min"  # noqa: S105


def _hs256(**claims: object) -> str:
    return jwt.encode({"sub": "u1", **claims}, _SECRET, algorithm="HS256")


@pytest.fixture(scope="module")
def rsa_keys() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


def test_hs256_valid_token_yields_principal_with_roles_and_scopes() -> None:
    auth = TokenAuthenticator(secret=_SECRET)
    token = _hs256(
        sub="alice",
        realm_access={"roles": ["fhir:read", "auditor"]},
        scope="openid patient/Patient.read",
    )
    principal = auth.authenticate(token)
    assert principal.subject == "alice"
    assert principal.has_role("fhir:read")
    assert "auditor" in principal.roles
    assert "patient/Patient.read" in principal.scopes


def test_rs256_token_validated_with_public_key(rsa_keys: tuple[str, str]) -> None:
    """The Keycloak path: token signed with the private key, verified with public."""
    private_pem, public_pem = rsa_keys
    token = jwt.encode(
        {"sub": "bob", "realm_access": {"roles": ["fhir:read"]}},
        private_pem,
        algorithm="RS256",
    )
    principal = TokenAuthenticator(public_key=public_pem).authenticate(token)
    assert principal.subject == "bob"
    assert principal.has_role("fhir:read")


def test_expired_token_rejected() -> None:
    auth = TokenAuthenticator(secret=_SECRET)
    token = _hs256(exp=int(time.time()) - 60)
    with pytest.raises(AuthError) as exc:
        auth.authenticate(token)
    assert exc.value.status_code == 401


def test_wrong_secret_rejected() -> None:
    token = jwt.encode({"sub": "x"}, "some-other-secret", algorithm="HS256")
    with pytest.raises(AuthError) as exc:
        TokenAuthenticator(secret=_SECRET).authenticate(token)
    assert exc.value.status_code == 401


def test_token_without_subject_rejected() -> None:
    token = jwt.encode({"realm_access": {"roles": []}}, _SECRET, algorithm="HS256")
    with pytest.raises(AuthError):
        TokenAuthenticator(secret=_SECRET).authenticate(token)


def test_unconfigured_authenticator_fails_closed() -> None:
    """No key/secret -> reject everything (never accept an unverifiable token)."""
    auth = TokenAuthenticator()
    assert not auth.configured
    with pytest.raises(AuthError) as exc:
        auth.authenticate(_hs256())
    assert exc.value.status_code == 401
