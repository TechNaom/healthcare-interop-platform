# AI Handoff

_Written so a different AI assistant (or human) can pick this repo up cold._
_Last updated: 2026-09-22._

## What this repo is

A HIPAA-aligned **HL7 v2 + FHIR (R4/R5) interoperability platform** — an
integration engine that ingests HL7 v2 messages, maps everything through **one
internal canonical model**, and exposes FHIR REST APIs, with HIPAA technical
safeguards (encryption, RBAC, append-only audit, Safe Harbor de-identification)
built in. Client engagement, **private** repo. Currently Python-only.

## Read these first, in order

1. [README.md](README.md) — orientation + doc map
2. [PROJECT_STATE.md](PROJECT_STATE.md) — current status, timeline, next task
3. [docs/SRS.md](docs/SRS.md) — formal requirements (FR-*/NFR-*)
4. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) + [docs/DESIGN.md](docs/DESIGN.md) — components & module map
5. [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — the canonical model (the core of the system)
6. [docs/DECISIONS.md](docs/DECISIONS.md) — the *why* behind every choice (9 ADRs)

## Design philosophy

- **One canonical model, never pairwise translators** ([ADR-001](docs/DECISIONS.md#adr-001)). HL7 and FHIR both map to/from the canonical model; all code targets the canonical model. Do not write a direct HL7→FHIR translator.
- **Platform-agnostic, container-first** ([ADR-003](docs/DECISIONS.md#adr-003)). No OS-specific paths (`pathlib`, not string paths), no cloud-vendor SDK in core logic. Everything self-hosts.
- **No cloud.** No AWS/Azure/GCP. Self-hosted Vault/MinIO/Postgres/Keycloak/Prometheus. Only external touchpoints are GitHub (source, ADR-004) and GitHub Actions CI (ADR-007) — both PHI-safe only because of the synthetic-data rule.
- **Pluggable infrastructure.** `KeyManager`, `SecretsProvider`, `ObjectStore`, `MessageBus`, DB access are **interfaces** with self-hosted reference implementations. Business logic never imports a vendor.
- **Confidential by default.** No outbound telemetry/log/error sink to third-party SaaS without a signed BAA.

## The one rule you must never break

**No real PHI. Anywhere. Ever.** ([ADR-005](docs/DECISIONS.md#adr-005)) Not in code,
fixtures, logs, commit messages, or an AI chat session. All dev/test/demo data
is **synthetic** (Synthea). A private repo is *not* a PHI control — the rule
holds regardless. `.gitignore` blocks `/data/real/`, `/data/patients/`, `*.phi`,
secrets, and keys; `gitleaks` runs in pre-commit + CI.

## Tech stack (settled — see [docs/TECH_STACK.md](docs/TECH_STACK.md))

Python 3.12 · FastAPI · `fhir.resources` · `python-hl7` + custom asyncio MLLP ·
SQLAlchemy 2.x async + Alembic · PostgreSQL 16 · Keycloak (OIDC) · Vault · MinIO ·
Traefik · Prometheus/Grafana/OpenTelemetry · pytest + testcontainers + Synthea ·
Docker/Buildx/Compose · GitHub Actions · `uv` · ruff · mypy · bandit · gitleaks.

## Naming & layout conventions

- Python package root: **`hip/`** (under `src/`). Design-doc module names are
  bare (`gateway.auth`); in code they're `hip.gateway.auth`, `hip.messaging.hl7.listener`, etc.
- The roadmap's `platform/` shim is **`hip.platform`** (renamed to avoid
  shadowing the stdlib `platform` module).
- `src/` layout, tests in `tests/`, one module = one responsibility per
  [docs/DESIGN.md §1](docs/DESIGN.md#1-module-breakdown).

## Current state

Functional pilot core complete, all on `main` (direct-to-main workflow, no
PRs/branches, since 2026-08-25). The full pipeline runs end to end against real
Postgres/Docker: HL7 v2 over MLLP → parse/route/map → encrypted persistence +
audit → de-id copy → JWT+RBAC+minimum-necessary-gated FHIR R4 API. FHIR resource
set (all read+write): Patient/Encounter/Observation/ServiceRequest/
DiagnosticReport; identifier search on Patient/Encounter/Observation/
DiagnosticReport. Plus rate limiting, OTel metrics, real Keycloak JWKS +
Vault-backed keys, a Helm chart (self-hosted + cloud overlay + Terraform
reference), a synthetic-population generator, DB-grant compliance tests, and full
observability (structured logs + OTel metrics + distributed tracing). See
[PROJECT_STATE.md](PROJECT_STATE.md) for what's still open (more ingestion
transports, standing up the cloud reference, C++ validator).

## What NOT to change without a new ADR

- The canonical-model-first approach (ADR-001).
- The synthetic-data-only rule (ADR-005) — non-negotiable.
- Introducing any cloud provider or swapping a self-hosted component for a
  third-party SaaS (would need a BAA).
- Reviving C++ now (ADR-006 defers it) or hand-rolling JWT auth instead of
  Keycloak (ADR-008 decided against it).

## Current & next task

See [PROJECT_STATE.md](PROJECT_STATE.md) "Next recommended task": Synthea bulk
fixtures, FHIR search for Encounter/Observation, or DiagnosticReport — in that
rough priority order. The cloud-native variant comes only after those, per the
2026-08-25 deployment decision (self-hosted core first).
