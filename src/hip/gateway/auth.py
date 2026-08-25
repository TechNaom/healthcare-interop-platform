"""Authentication and authorization — the single enforcement point.

Maps to ``gateway.auth`` in docs/DESIGN.md 1. Validates a bearer JWT issued by
Keycloak (ADR-008) and derives a ``Principal`` (subject + realm roles + scopes);
Keycloak owns identity and token issuance, the authorization *decision* lives
here. RBAC is enforced per route via ``require_role``.

Fail-closed: if no verification key/secret is configured, every request is
rejected (401). PHI is never reachable without a validated token.

Verification is done with a configured key so the platform never has to trust a
token it can't check:
* ``HIP_JWT_PUBLIC_KEY`` (RS256) — the realm's public key, as Keycloak exposes;
* or ``HIP_JWT_SECRET`` (HS256) — for simpler/self-contained setups and tests.
Live JWKS fetch from Keycloak is a thin follow-on (swap the key source).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import jwt


class AuthError(Exception):
    """Authentication/authorization failure. ``status_code`` is 401 or 403."""

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code  # FHIR issue code, e.g. "login"/"forbidden"
        self.detail = detail


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller."""

    subject: str
    roles: frozenset[str] = field(default_factory=frozenset)
    scopes: frozenset[str] = field(default_factory=frozenset)

    def has_role(self, role: str) -> bool:
        return role in self.roles


class TokenAuthenticator:
    """Validates JWTs and extracts a Principal. Configured once, used per request."""

    def __init__(
        self,
        *,
        public_key: str | None = None,
        secret: str | None = None,
        issuer: str | None = None,
        audience: str | None = None,
    ) -> None:
        self._public_key = public_key
        self._secret = secret
        self._issuer = issuer
        self._audience = audience

    @property
    def configured(self) -> bool:
        return bool(self._public_key or self._secret)

    def authenticate(self, token: str) -> Principal:
        if not self.configured:
            # Secure default: never accept a token we cannot verify.
            raise AuthError(401, "login", "authentication is not configured")

        if self._public_key:
            key: str = self._public_key
            algorithms = ["RS256"]
        elif self._secret is not None:
            key = self._secret
            algorithms = ["HS256"]
        else:  # pragma: no cover - guarded by the ``configured`` check above
            raise AuthError(401, "login", "authentication is not configured")

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=algorithms,
                issuer=self._issuer,
                audience=self._audience,
                options={"verify_aud": self._audience is not None},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(401, "login", f"invalid token: {type(exc).__name__}") from exc

        subject = claims.get("sub")
        if not subject:
            raise AuthError(401, "login", "token has no subject")

        realm_access = claims.get("realm_access") or {}
        roles = frozenset(realm_access.get("roles", []))  # Keycloak realm roles
        scopes = frozenset((claims.get("scope") or "").split())
        return Principal(subject=subject, roles=roles, scopes=scopes)


def authenticator_from_env() -> TokenAuthenticator:
    """Build an authenticator from environment configuration."""
    return TokenAuthenticator(
        public_key=os.environ.get("HIP_JWT_PUBLIC_KEY"),
        secret=os.environ.get("HIP_JWT_SECRET"),
        issuer=os.environ.get("HIP_JWT_ISSUER"),
        audience=os.environ.get("HIP_JWT_AUDIENCE"),
    )
