# Security & compliance

**Status:** Draft. This document describes intended controls for a HIPAA-*aligned* platform. It is not a substitute for a formal HIPAA Security Risk Assessment, legal BAA review, or third-party audit — those are explicitly out of scope for the initial build (see [roadmap](<../Healthcare Interop Platform.md#out-of-scope-for-either-track--and-why-more-weeks-wouldnt-fix-it>)) and gated on the client's own compliance process.

## 1. HIPAA Security Rule — technical safeguards mapping

Technical safeguards focus on the technology and processes that protect ePHI as it's stored and transmitted electronically — ensuring only authorized users can access data, and that all activity is traceable and secure.

| Safeguard (45 CFR §164.312) | How this architecture addresses it |
|---|---|
| **Access Control** (`§164.312(a)`) | Unique user/service IDs, token-based login (OAuth 2.0/OIDC), **RBAC** (role) combined with **ABAC** (attribute — e.g. patient-specific vs. population scope) enforced centrally in the Gateway's `AuthZ` module; field-level filtering in the PHI repository; no anonymous access path; automatic logoff/session-expiry on interactive sessions and long-lived tokens ([SRS §5.1](SRS.md#51-access-control)) |
| **Audit Controls** (`§164.312(b)`) | Every PHI read/write produces an immutable, append-only audit entry — identity, resource, operation, timestamp, source ([SRS §5.4](SRS.md#54-audit-logging)) |
| **Integrity** (`§164.312(c)`) | Canonical model validation at ingestion rejects malformed data before persistence; append-only audit log so history can't be silently altered; checksum/hash verification for stored large payloads where appropriate ([SRS §5.5](SRS.md#55-integrity-and-validation)) |
| **Person or Entity Authentication** (`§164.312(d)`) | Strong authentication required for all API access — token-based (OAuth 2.0/OIDC) at minimum; no unauthenticated path to clinical endpoints |
| **Transmission Security** (`§164.312(e)`) | TLS 1.2+ / HTTPS for all external traffic; MLLP channels tunneled over secure VPN or TLS; internal PHI-zone services not exposed to public ingress (see [ARCHITECTURE.md §3](ARCHITECTURE.md#3-deployment-view)) |

## 2. Access control — detail

- **Authentication:** unique user/service IDs, strong password policy where passwords are used at all, token-based login via OAuth 2.0/OpenID Connect.
- **Authorization:** RBAC (roles below) layered with ABAC where role alone can't express the rule (e.g. "this clinician, this patient population only").
- **Automatic logoff:** interactive sessions and issued tokens both expire; no indefinitely-lived session is left exploitable if a workstation is unattended.
- **Minimum necessary by default:** API response models filter non-required fields per endpoint/use case — the filtering happens server-side, not left to the caller to discard extra fields.
- **Institutional SSO/SAML federation:** requested in the detailed SRS, but the original roadmap scoped full SSO/SAML federation *out* of the initial build (needs a real institutional IdP, a separate procurement conversation). Baseline OAuth2/OIDC token auth covers the initial build either way — **open item**, see [SRS §11](SRS.md#11-open-items-and-conflicts--not-silently-resolved).

## 3. Encryption

- **At rest:** AES-256 disk encryption for the PHI store and backups; keys retrieved through `KeyManager`, never embedded in config or code.
- **In transit:** TLS 1.2+ / HTTPS for all external traffic; internal gRPC/HTTP traffic between services stays inside the container network's internal zone (not publicly routable).
- **Application-layer encryption:** available as defense-in-depth for especially high-risk PHI fields, on top of at-rest encryption — not a replacement for it.
- **Key rotation:** `KeyManager.rotate_key()` is part of the interface contract from day one, even though the reference Vault implementation is the only backend wired up initially.

## 4. RBAC — initial role set

| Role | Access |
|---|---|
| **Integration Administrator** | Configure routing/credentials, view system health — no direct PHI field access beyond what's needed to diagnose a routing failure |
| **Clinical API Consumer** | Read/write FHIR resources per their authorized scope (resource type and/or patient population, via RBAC+ABAC) |
| **Auditor / Compliance Officer** | Read audit log metadata; explicitly does **not** get raw clinical field values through this role alone |
| **Analytics/AI Consumer** | Read-only, de-identified store only — no role grants direct PHI-store access for analytics use cases |

Roles are enforced in `gateway.auth`, not scattered as ad hoc checks across endpoint handlers ([SRS §5.1](SRS.md#51-access-control)).

## 5. Audit logging

- Every ePHI access/mutation logs: user/service identity, patient/resource identifier, operation (create/read/update/delete/search), timestamp, source IP/host.
- Written to an immutable/WORM-capable store (object-lock storage or an append-only DB) — no code path updates or deletes an existing entry.
- Retention: commonly referenced at 6 years for HIPAA-adjacent audit trails — **not confirmed against this client's actual regulatory obligation**, treat as a placeholder until confirmed (see [SRS §11](SRS.md#11-open-items-and-conflicts--not-silently-resolved)).
- Logging is standardized across the codebase (one structured-logging library, one event shape) so Python (and, later, C++) components all forward to the same sink.
- **AI-assisted anomaly detection over audit logs** — requested capability, treated as future/optional. A self-hosted anomaly-detection component needs no BAA; a third-party "cybersecurity AI" service would need one first, like any other third party touching audit metadata. Which approach is wanted is unconfirmed — see [SRS §11](SRS.md#11-open-items-and-conflicts--not-silently-resolved).

## 6. Integrity controls

- Schema validation for every HL7 v2 message and FHIR resource before persistence or downstream processing — malformed input never reaches the PHI store.
- Checksum/hash-based integrity verification for stored documents or large payloads where appropriate.
- Validation errors are logged and surfaced through monitoring/alerting, not silently dropped into a dead-letter store with no signal.
- Append-only audit log doubles as an integrity control — a record's history can't be quietly rewritten.

## 7. De-identification

Applies Safe Harbor (45 CFR §164.514(b)(2)) — all 18 identifier categories are stripped or generalized before a record enters the de-identified store:

1. Names
2. Geographic subdivisions smaller than state (generalized to state or larger where required)
3. Dates (birth, admission, discharge, death) more precise than year, and ages over 89
4. Telephone numbers
5. Fax numbers
6. Email addresses
7. Social Security numbers
8. Medical record numbers
9. Health plan beneficiary numbers
10. Account numbers
11. Certificate/license numbers
12. Vehicle identifiers
13. Device identifiers/serial numbers
14. URLs
15. IP addresses
16. Biometric identifiers
17. Full-face photos and comparable images
18. Any other unique identifying number, characteristic, or code

Scope for the initial build is **structured-field de-identification**. Free-text/unstructured note de-identification (NER-based) is explicitly deferred to its own future phase — a different, probabilistic/ML-based problem from stripping known structured fields.

## 8. Third-party services & BAAs

**Hard rule, not a default:** nothing that touches real PHI goes near a third-party service — AI code review tools, SaaS linters, cloud NLP APIs, error-reporting SaaS, third-party audit-log AI — without a signed BAA in place first. Absent that, every pluggable interface (`KeyManager`, `ObjectStore`, `MessageBus`, observability export) defaults to a self-hosted reference implementation ([SRS §7.3](SRS.md#73-observability), [SRS §12](SRS.md#12-constraints-and-assumptions)).

This repository itself contains **no real PHI** at any point — see [ADR-005](DECISIONS.md#adr-005). All fixtures, examples, and demo data used during development are synthetic.

## 9. Deferred / explicitly out of scope

- Formal third-party penetration testing and SAST/DAST audit cycles — vendor-scheduled, and shouldn't run against real PHI regardless without a BAA.
- Full OAuth2/OIDC + SAML SSO federation — open item, see [SRS §11](SRS.md#11-open-items-and-conflicts--not-silently-resolved).
- Formal incident-response runbook — written once the system it describes is stable, not speculatively now.
- HIPAA Security Risk Assessment sign-off — a client-side legal/compliance process this document supports but does not replace.
