# Security & compliance

**Status:** Draft. This document describes intended controls for a HIPAA-*aligned* platform. It is not a substitute for a formal HIPAA Security Risk Assessment, legal BAA review, or third-party audit — those are explicitly out of scope for the initial build (see [roadmap](<../Healthcare Interop Platform.md#out-of-scope-for-either-track--and-why-more-weeks-wouldnt-fix-it>)) and gated on the client's own compliance process.

## 1. HIPAA Security Rule — technical safeguards mapping

| Safeguard (45 CFR §164.312) | How this architecture addresses it |
|---|---|
| **Access Control** (`§164.312(a)`) | RBAC enforced centrally in the Gateway's `AuthZ` module; field-level filtering in the PHI repository; no anonymous access path ([FR-6.1](SRS.md#56-security--identity), [FR-6.2](SRS.md#56-security--identity)) |
| **Audit Controls** (`§164.312(b)`) | Every PHI read/write produces an immutable, append-only audit entry ([FR-4.2](SRS.md#54-persistence), [FR-4.3](SRS.md#54-persistence)) |
| **Integrity** (`§164.312(c)`) | Canonical model validation at ingestion (C++ validator) rejects malformed data before persistence; audit log is append-only so history can't be silently altered |
| **Person or Entity Authentication** (`§164.312(d)`) | All API access requires authentication (token or mTLS); no unauthenticated path to clinical endpoints |
| **Transmission Security** (`§164.312(e)`) | TLS terminated at the Gateway; internal PHI-zone services not exposed to public ingress (see [ARCHITECTURE.md §3](ARCHITECTURE.md#3-deployment-view)) |

## 2. Encryption

- **At rest:** PHI store encrypted at rest; encryption keys retrieved through `KeyManager`, never embedded in config or code.
- **In transit:** TLS for all external traffic; internal gRPC traffic between Python and C++ services runs inside the container network's internal zone (not publicly routable).
- **Key rotation:** `KeyManager.rotate_key()` is part of the interface contract from day one, even though the reference Vault implementation is the only backend wired up initially.

## 3. RBAC — initial role set

| Role | Access |
|---|---|
| **Integration Administrator** | Configure routing/credentials, view system health — no direct PHI field access beyond what's needed to diagnose a routing failure |
| **Clinical API Consumer** | Read/write FHIR resources per their authorized scope (e.g., a given resource type, given patient population) |
| **Auditor / Compliance Officer** | Read audit log metadata; explicitly does **not** get raw clinical field values through this role alone |
| **Analytics/AI Consumer** | Read-only, de-identified store only — no role grants direct PHI-store access for analytics use cases |

Roles are enforced in `gateway.auth`, not scattered as ad hoc checks across endpoint handlers ([FR-6.2](SRS.md#56-security--identity)).

## 4. De-identification

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

Scope for the initial build is **structured-field de-identification** (the list above, applied to canonical model fields). Free-text/unstructured note de-identification (NER-based) is explicitly deferred — flagged in the roadmap as its own future phase, since it's a different (probabilistic, ML-based) problem from stripping known structured fields.

## 5. Third-party services & BAAs

**Hard rule, not a default:** nothing that touches real PHI goes near a third-party service — AI code review tools, SaaS linters, cloud NLP APIs, error-reporting SaaS — without a signed BAA in place first. Absent that, every pluggable interface (`KeyManager`, `ObjectStore`, `MessageBus`, observability export) defaults to a self-hosted reference implementation ([NFR-5](SRS.md#6-non-functional-requirements), [NFR-6](SRS.md#6-non-functional-requirements)).

This repository itself contains **no real PHI** at any point — see [ADR-005](DECISIONS.md#adr-005). All fixtures, examples, and demo data used during development are synthetic.

## 6. Deferred / explicitly out of scope

Per the roadmap, and repeated here because they're compliance-adjacent and easy to assume are "done" when they're not:

- Formal third-party penetration testing and SAST/DAST audit cycles — vendor-scheduled, and shouldn't run against real PHI regardless without a BAA.
- Full OAuth2/OIDC + SAML SSO federation — needs a real institutional IdP, a separate procurement conversation.
- Formal incident-response runbook — written once the system it describes is stable, not speculatively now.
- HIPAA Security Risk Assessment sign-off — a client-side legal/compliance process this document supports but does not replace.
