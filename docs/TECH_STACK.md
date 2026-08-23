# Tech stack

**Status:** Settled. Every choice below is decided and traced to an ADR or requirement — this is the complete build list.

Companion to [TECHNOLOGY_MAPPING.md](TECHNOLOGY_MAPPING.md), which answers *"for requirement X, what are we using?"*. This document answers *"what is the complete stack, and what do I need installed?"*

---

## The short answer

| Question | Answer |
|---|---|
| **Cloud account needed?** | **No.** Nothing depends on AWS/Azure/GCP. Every component self-hosts. |
| **Docker needed?** | **Yes — required.** Containers *are* the architecture, not a packaging afterthought. |
| **Kubernetes needed?** | **Not for this build.** Compose covers local dev and pilot. K8s is a later deployment target, not a build dependency. |
| **DevOps needed?** | **Yes** — CI, builds, migrations, seeding. Just not *cloud* DevOps. |

The distinction that matters: **containerization ≠ cloud**. We containerize so the system runs identically anywhere — a laptop, an on-prem server, or any Kubernetes distribution — precisely so no cloud vendor is required ([ADR-003](DECISIONS.md#adr-003)).

---

## Application stack — what we write

| Layer | Technology | Why |
|---|---|---|
| Language | **Python 3.12** | Per [ADR-006](DECISIONS.md#adr-006) — C++ is benched, not current scope |
| Web framework | **FastAPI** | Async, Pydantic-native (pairs directly with `fhir.resources`), automatic OpenAPI docs |
| FHIR modeling | **`fhir.resources`** | Pydantic-based FHIR R4/R5 models — chosen over `fhirclient` because it drops into FastAPI typing with no adapter layer |
| HL7 v2 parsing | **`python-hl7`** + custom asyncio MLLP listener | MLLP framing is simple enough (`<VT>msg<FS><CR>`) that a dedicated dependency isn't warranted |
| ORM / DB access | **SQLAlchemy 2.x** (async) | Repository layer behind the `persistence.*` interfaces — business logic never holds a connection |
| Migrations | **Alembic** | Schema versioning; required from day one, not bolted on later |
| Structured logging | **`structlog`** | One event shape across every module, feeding the audit path |
| Validation | **Pydantic v2** | Already the FastAPI/`fhir.resources` foundation |

## Infrastructure stack — what we run (all containers, all self-hosted)

| Component | Technology | Role |
|---|---|---|
| Database | **PostgreSQL 16** | Relational canonical entities + JSONB for FHIR extensions; separate instances/schemas for PHI, dead-letter, audit, de-identified |
| Identity provider | **Keycloak** | OIDC now, SAML available if federation is confirmed — [ADR-008](DECISIONS.md#adr-008) |
| Secrets / keys | **HashiCorp Vault** | Backs the `KeyManager` and `SecretsProvider` interfaces; never a cloud KMS |
| Object storage | **MinIO** | S3-compatible, self-hosted; backs `ObjectStore` when a phase needs blobs |
| Reverse proxy / TLS | **Traefik** | TLS 1.2+ termination, cert lifecycle; keeps TLS out of the FastAPI process |
| Metrics | **Prometheus** | Scrapes OpenTelemetry metrics |
| Dashboards | **Grafana** | Self-hosted; no Datadog/New Relic/third-party APM |
| Tracing/metrics SDK | **OpenTelemetry** | Vendor-neutral, export target configurable and internal by default |

Every one of these is open-source and self-hostable — a deliberate consequence of the no-SaaS-without-BAA rule ([SECURITY_AND_COMPLIANCE.md §8](SECURITY_AND_COMPLIANCE.md#8-third-party-services--baas)).

## Testing stack

| Purpose | Technology |
|---|---|
| Test runner | **`pytest`** |
| Container lifecycle in tests | **`testcontainers`** — real Postgres/Keycloak per test run, not mocks |
| Synthetic patient data | **Synthea** (MITRE) — realistic FHIR R4 + HL7 v2 populations |
| API client | **`httpx`** (async) |
| Property-based testing | **`hypothesis`** — generates parser edge cases we wouldn't write by hand |
| Load testing | **`locust`** |
| Coverage | **`pytest-cov`** |

Full rationale in [TEST_STRATEGY.md](TEST_STRATEGY.md).

## Build, packaging & CI

| Purpose | Technology |
|---|---|
| Containerization | **Docker**, multi-stage builds |
| Multi-arch images | **Docker Buildx** — `linux/amd64` + `linux/arm64` per [ADR-003](DECISIONS.md#adr-003) |
| Local orchestration | **Docker Compose** — the entire stack, one command |
| CI | **GitHub Actions** on the private repo — [ADR-007](DECISIONS.md#adr-007) |
| Dependency management | **`uv`** or **Poetry** — lockfile-based, reproducible builds |
| Linting | **`ruff`** |
| Type checking | **`mypy`** |
| Security linting | **`bandit`** |
| Secret scanning | **`gitleaks`** in CI + pre-commit — PHI/secret leakage is the failure mode that matters most here |
| Pre-commit hooks | **`pre-commit`** — runs the above before a commit lands |

## What you need installed locally

| Tool | Status on this machine | Notes |
|---|---|---|
| **Python 3.12** | ✅ Installed | |
| **Git** | ✅ Installed | |
| **GitHub CLI** | ✅ Installed & authenticated | |
| **Docker Desktop** | ❌ **Not installed — required before Phase 0** | Everything else runs inside it |
| Java runtime | Optional | Only to *run* Synthea locally; the generated fixtures are committed, so most work doesn't need it |

Nothing else. No cloud CLI, no `kubectl`, no Terraform, no C++ toolchain.

## Explicitly not used, and why

| Not using | Why |
|---|---|
| **Any cloud provider SDK** | [ADR-003](DECISIONS.md#adr-003) — no vendor SDK in core logic; pluggable interfaces with self-hosted implementations instead |
| **Cloud KMS** (AWS KMS, Azure Key Vault…) | Vault self-hosted, same reason |
| **Managed database** (RDS, Cloud SQL…) | Postgres in a container; a client can point at a managed instance later — the abstraction layer makes that a config change |
| **Kubernetes** | Not needed to build or pilot; deployment-target decision, and every image is OCI so it stays available |
| **Third-party APM/SIEM/error reporting** | Would send data off-platform; needs a BAA. Self-hosted Prometheus/Grafana instead |
| **C++ toolchain** | Benched — [ADR-006](DECISIONS.md#adr-006) |
| **Kafka / RabbitMQ** | The `MessageBus` interface exists, but no phase currently needs async decoupling. Not introduced speculatively |

## Where Kubernetes *would* enter

Not now — but the path is deliberate, so it stays cheap:

1. Every service already ships as a multi-arch OCI image built in CI.
2. Every service already exposes `/healthz` and `/readyz` for liveness/readiness probes.
3. All configuration comes from environment variables and mounted files — no baked-in config.
4. All infrastructure dependencies sit behind interfaces, so a managed Postgres or a cluster-native secrets store swaps in by configuration.

Writing manifests or a Helm chart is then a deployment task against a known target — not a re-architecture. That's the whole point of ADR-003.
