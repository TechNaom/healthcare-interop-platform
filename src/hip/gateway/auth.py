"""Authentication and authorization — the single enforcement point.

Maps to ``gateway.auth`` in docs/DESIGN.md section 1. AuthN via token (OIDC,
issued by Keycloak — ADR-008) or mTLS; AuthZ via RBAC + ABAC (SRS section 5.1).
Keycloak supplies identity and tokens; the authorization *decision* lives here,
not in Keycloak. Shared by both the FHIR and admin API groups. Implemented in
Phase 9.
"""
