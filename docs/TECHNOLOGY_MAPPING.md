# Requirement → technology mapping

One-page answer to "for this requirement, what are we actually using." Organized to match [SRS.md](SRS.md) section-for-section. Two items below are marked **proposed, not yet confirmed** — everything else is already locked in across the other docs; this page just puts it in one place.

## Architecture (SRS §3)

| Component | Technology |
|---|---|
| Integration Gateway | Python 3.12, **FastAPI** |
| Messaging Engine | Python (HL7 parse/route/transform) — **C++ benched, not current scope** ([ADR-006](DECISIONS.md#adr-006)) |
| Database | **PostgreSQL** — relational, chosen over a document DB. Core canonical entities (Patient, Encounter, Observation, Order) as relational tables; JSONB columns for FHIR extensions/nested fields that don't fit a fixed column — gets document-like flexibility without adopting a second database technology. Accessed through a repository layer (SQLAlchemy) behind the `persistence.*` module interfaces in [DESIGN.md](DESIGN.md#1-module-breakdown), never queried directly from business logic — that's what keeps NFR-5 (swappable DB) real instead of aspirational. |
| Encryption at rest | AES-256 (Postgres-native disk/tablespace encryption or underlying volume encryption, depending on final host) |
| Centralized audit logging | Append-only **Postgres table**, immutability enforced at the DB permission level (`REVOKE UPDATE, DELETE` for the application role) — not just an application-level promise. No separate WORM service needed at this scale; MinIO object-lock is the documented upgrade path if a stronger guarantee is ever required. |

## Functional requirements (SRS §4)

| Requirement | What we're using |
|---|---|
| **4.1 HL7 v2 message handling** | `python-hl7` for parsing/structure. MLLP transport: a small asyncio TCP listener implementing MLLP framing directly (`<VT>message<FS><CR>`) — MLLP framing is simple enough that a dedicated dependency isn't worth adding. HTTP and file-drop ingestion are plain FastAPI routes / a watched directory respectively. |
| **4.2 FHIR API services** | FastAPI REST layer + **`fhir.resources`** (Pydantic-based FHIR models) for typed resources, validation, and serialization — this pairing is why `fhir.resources` was picked over `fhirclient`: it's Pydantic-native, so it drops straight into FastAPI's request/response typing with no adapter layer. |
| **4.4 Data storage and access** | Storing: PostgreSQL, as above, one schema/instance for PHI, a physically separate one for the de-identified store, per [SRS §4.4.3](SRS.md#44-data-storage-and-access). Accessing: repository classes (`persistence.phi_repo`, `persistence.deid_repo`, `persistence.audit_log`) — the only code allowed to hold a DB connection. |

## Security requirements (SRS §5)

| Requirement | What we're using |
|---|---|
| **5.1 Access control** | Token-based auth (OAuth 2.0/OIDC bearer tokens), RBAC+ABAC checks centralized in `gateway.auth`. **Proposed, not yet confirmed:** issue/validate JWTs directly in the Gateway (`python-jose` or `PyJWT`) for the pilot — no separate identity-provider service to stand up. If full SSO/SAML federation gets confirmed as in-scope (still open, [SRS §11](SRS.md#11-open-items-and-conflicts--not-silently-resolved)), the natural upgrade is **self-hosted Keycloak**, since it speaks both OIDC and SAML — swapping to it later doesn't change the RBAC/ABAC logic, only where tokens come from. |
| **5.2 Transmission security** | TLS 1.2+ terminated at a reverse proxy in front of the Gateway — **Traefik** (Compose/K8s-native, picks up cert renewal cleanly) rather than building TLS into the FastAPI process itself. |
| **5.3 Encryption** | At rest: AES-256 (above). In transit: TLS 1.2+ (above). Keys: **HashiCorp Vault**, self-hosted, via the `KeyManager` interface — never a cloud KMS. |
| **5.4 Audit logging** | Append-only Postgres table (above) + `structlog` for structured application logging, one event shape across every module. AI-assisted anomaly detection over the audit log is still an **open item** ([SRS §11](SRS.md#11-open-items-and-conflicts--not-silently-resolved)) — not built until you confirm self-hosted vs. third-party. |
| **5.5 Integrity & validation** | Schema validation via `fhir.resources` (FHIR) and `python-hl7` (HL7 structure) at ingestion. Payload integrity: SHA-256 checksums (Python `hashlib`) on stored large payloads. |
| **Privacy / de-identification (§6)** | Structured-field Safe Harbor rules: a Python module operating directly on the canonical model fields already mapped in [DATA_MODEL.md](DATA_MODEL.md) — this is plain field transformation (drop/generalize/date-shift), not a library dependency. Unstructured-text de-id (deferred, per roadmap) would use **Presidio** (Microsoft, open-source, self-hostable — no BAA needed since nothing leaves your infrastructure) when that phase is scheduled. |

## Non-functional requirements (SRS §7)

| Requirement | How it's handled |
|---|---|
| **7.1 Performance/scalability** | FastAPI's async I/O for concurrency; horizontal scaling is just more container replicas behind Traefik (Compose: fixed replica count; a real K8s deployment later could add HPA, not needed for a pilot). |
| **7.2 Reliability/availability** | Pilot scope: single-instance per service with Compose `restart: unless-stopped`. Multi-region/HA is explicitly deferred per the roadmap — not built now, not silently promised either. |
| **7.3 Observability** | **OpenTelemetry** SDK in every Python service, exporting to a **self-hosted Prometheus + Grafana** stack (metrics/dashboards) via Compose — no Datadog/New Relic/third-party APM, consistent with the no-SaaS-without-BAA rule. |
| **Cloud?** | **Not required.** Everything above is self-hosted and runs on this machine or any container host. If you want a cloud deployment later, that's a deployment-target decision you make when you're ready to provision it — nothing here depends on it existing. |

## Technology stack (SRS §8) — consolidated

| Layer | Choice |
|---|---|
| Web framework | FastAPI |
| FHIR modeling | `fhir.resources` |
| HL7 v2 parsing | `python-hl7` + custom asyncio MLLP listener |
| Database | PostgreSQL + SQLAlchemy |
| Reverse proxy / TLS | Traefik |
| KeyManager | HashiCorp Vault (self-hosted) |
| ObjectStore | MinIO (self-hosted, if/when a phase needs blob storage) |
| Observability | OpenTelemetry → Prometheus + Grafana (self-hosted) |
| Logging | `structlog` |
| Auth | JWT (proposed) → Keycloak (future, only if SSO/SAML confirmed) |
| Testing | `pytest` |
| CI | GitHub Actions on the private repo ([ADR-007](DECISIONS.md#adr-007)) |
| Static analysis | `ruff` (lint), `mypy` (types), `bandit` (security lint) — run in CI |
| Packaging | Docker, multi-stage, multi-arch (`linux/amd64` + `linux/arm64`) |

## Compliance, documentation & governance (SRS §9) / Testing (SRS §10)

Already answered in detail — not repeated here, see [SRS §9](SRS.md#9-compliance-documentation-and-governance) and [SRS §10](SRS.md#10-implementation-and-testing-requirements) directly: data-flow diagram lives in [ARCHITECTURE.md](ARCHITECTURE.md) as a living document; traceability matrix and incident-response runbook are deferred until the system is stable (roadmap rationale); testing is `pytest` unit + integration + compliance tests, synthetic fixtures only, run in the CI above.

## Source references

Carried over from the client-provided detailed SRS, for provenance:

1. https://sapientcodelabs.com/blogs/how-to-implement-hl7-fhir-integration-with-python-and-fastapi-for-healthcare-systems
2. https://alexmayhew.dev/services/python-developer-for-healthcare
3. https://github.com/HL7/fhir
4. https://pypi.org/project/fhir.resources/
5. https://confluence.hl7.org/spaces/FHIR/pages/35718838/Open+Source+Implementations
6. https://github.com/dmooney/fhircpp — future C++ phase reference only, not used in the current Python-only build

## What still needs your sign-off before Phase 0

Everything above is either already-decided-elsewhere or a low-risk default. Two things aren't:

1. **Auth: JWT-in-Gateway vs. Keycloak from day one.** JWT is simpler and matches "no SSO/SAML for the pilot." If you already know you want Keycloak (e.g. because SSO is coming soon regardless), better to start there than migrate later.
2. **Audit-log AI monitoring** — still needs your answer on self-hosted vs. third-party (unchanged from before).

Everything else in this document is ready to build against as soon as you say go.
