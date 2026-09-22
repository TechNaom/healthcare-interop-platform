# Project State

_Living status doc. Update at the end of every meaningful work session._
_Last updated: 2026-09-22._

## What this is

A HIPAA-aligned HL7 v2 + FHIR (R4/R5) interoperability platform. Python-only
for the current build (C++ high-throughput validation is a documented future
phase — [ADR-006](docs/DECISIONS.md#adr-006)). Containers are the deployment
unit. Full context: [README.md](README.md) → [Healthcare Interop Platform.md](<Healthcare Interop Platform.md>)
→ `docs/`.

## Current status

**~90% of the AI-compressed pilot scope. Direct-to-`main` workflow (no PRs/branches, per 2026-08-25 decision) — every phase below is merged and CI-green.**

Working end to end, verified against real Postgres and (for the core stack)
real Docker: **HL7 v2 over MLLP → parse/route/map to the canonical model →
encrypted persistence + append-only audit → de-identified copy →
JWT-authenticated + RBAC-gated + minimum-necessary-filtered FHIR R4 API**
(Patient/Encounter/Observation/ServiceRequest, read + write + blind-index
search on Patient), plus rate limiting, OTel metrics, a Helm chart, and DB-grant
compliance tests (audit immutability, store separation). All HIPAA technical
safeguards from `docs/SECURITY_COMPLIANCE.md` are implemented at least once.

**Just landed (this session):** real Keycloak JWKS support in `gateway.auth`
(`HIP_JWT_JWKS_URL`, live per-token key lookup by `kid`) and Vault-backed
`KeyManager`/`BlindIndexer` (`security.vault`, KV-v2 read, takes priority over
the static `HIP_ENCRYPTION_KEY`/`HIP_BLIND_INDEX_KEY` env vars when
`HIP_VAULT_ADDR` is set). `docker-compose.infra.yml` wires the `keycloak` +
`vault` services (behind the `infra` profile) into `app`/`mllp`; `minio` stays
declared-but-unwired since no phase needs blob storage yet.

**Still open** (roughly in priority order): Synthea bulk fixtures for
realistic-volume demo/perf data; FHIR search for Encounter/Observation
(currently Patient-only); DiagnosticReport resource (HL7 OBR-25, a documented
deferral since the ADR-001 review); cloud-native variant (self-hosted core is
deliberately built first, per the 2026-08-25 deployment decision).

For the detailed build log (every phase, commit, and gotcha), see the
`project-healthcare-interop-platform` memory record — this file stays a
high-level snapshot.

### ADR-001 gate: cleared 2026-08-25
The canonical model was reviewed against `docs/DATA_MODEL.md` v0.2.0 and HL7/FHIR
correctness (findings: 1 comment typo fixed; DiagnosticReport/OBR-25 remains a
documented deferral).

## Timeline — 12-week AI-orchestrated track

| Week | Focus | State |
|---|---|---|
| 1 | Foundations only | ✅ merged |
| 2 | Canonical model: drafted, revised, signed off | ✅ model built + ADR-001 gate cleared |
| 3 | Skeletons (gRPC stub deferred — ADR-006) | ✅ gateway skeleton + health done |
| 4–5 | HL7 ingestion built, then hardened | ✅ MLLP listener + parse + route + ACK/NACK |
| 6 | HL7→FHIR mapping, FHIR CRUD core | ✅ HL7→canonical + canonical→FHIR; Patient/Encounter/Observation/ServiceRequest read+write |
| 7 | FHIR completeness | 🔨 Patient search (blind index) done; Encounter/Observation search + DiagnosticReport still open |
| 8 | Python validator hardening (C++ deferred — ADR-006) | ⬜ |
| 9 | Persistence, RBAC, audit log, KeyManager | ✅ Postgres+Alembic, encryption at rest, JWT auth + RBAC + minimum-necessary, real Keycloak JWKS + Vault-backed keys |
| 10 | Safe Harbor de-id, OpenTelemetry | ✅ de-id store + OTel metrics/Prometheus done; full distributed tracing not yet |
| 11 | Integration testing + bug-fix buffer | 🔨 DB-grant compliance tests, rate limiting, Helm chart, compose demo done; Synthea bulk fixtures still open |
| 12 | Stabilization, demo, retrospective | ⬜ |

## Architecture decisions (authoritative log: [docs/DECISIONS.md](docs/DECISIONS.md))

- **ADR-001** — one canonical model, not pairwise HL7↔FHIR translators. Highest-leverage decision; gets its own reviewed spec before any parser/API code.
- **ADR-003** — container-first, platform-agnostic, multi-arch OCI images.
- **ADR-004** — private GitHub repo is the source of truth.
- **ADR-005** — synthetic data only, absolute. No real PHI anywhere, ever.
- **ADR-006** — Python-only now; C++ validator is a future phase behind the same module seam.
- **ADR-007** — GitHub Actions (hosted runners) for CI, safe because of ADR-005.
- **ADR-008** — self-hosted Keycloak for identity from day one.
- **ADR-009** — audit-log anomaly detection is self-hosted and out of initial scope.

### Scaffold-level decisions made this session (not yet promoted to ADRs)

- **Python package root is `hip/`** (Healthcare Interop Platform). The design
  docs name modules bare (`gateway.auth`, `messaging.hl7.listener`); in code
  these live under the `hip.` root (`hip.gateway.auth`, …). Reason: a
  top-level package literally named `platform/` would shadow the stdlib
  `platform` module — namespacing under `hip` avoids that footgun while
  keeping the doc's module names as the subpackage names. The `platform/`
  shim from the roadmap is `hip.platform`.
- **Dependency manager: `uv`** (TECH_STACK offered `uv` or Poetry). Chosen for
  speed and a single lockfile; revisit only if a blocker appears.
- **Runtime deps start empty.** Phase 0 stubs import stdlib only; each layer's
  real dependencies (fastapi, fhir.resources, sqlalchemy, …) get added in the
  phase that builds it, so the lockfile grows with actual usage.

## Repository layout

```
src/hip/
  platform/     OS-agnostic shim (pathlib-only helpers)      → hip.platform
  gateway/      FastAPI: FHIR + admin APIs, auth, ratelimit  → hip.gateway
    api/        fhir.py, admin.py
  messaging/    HL7 ingestion + canonical mapping + validate → hip.messaging
    hl7/        listener.py, parser.py, router.py
    canonical/  mapper.py
  validator.py
  persistence/  phi_repo, audit_log, deid_repo               → hip.persistence
  security/     keymanager, secrets, objectstore, deid       → hip.security
tests/          tiered by test type, selected via pytest markers
  unit/         fast in-process (scaffold smoke live)         -m unit
  integration/  2+ components vs testcontainers               -m integration
  regression/   module-surface golden (live) + future goldens -m regression
  performance/  locustfile + SRS 7.1 targets                  -m performance
  uat/          acceptance scenarios (docs/UAT_PLAN.md)        -m uat
```

## Testing (every sprint — see [docs/TEST_STRATEGY.md](docs/TEST_STRATEGY.md) section 8)

Four types run on a defined cadence, not as a one-off phase:
- **Unit + regression** — every PR (`pytest -m "not performance and not uat"`).
  Regression is live now via a module-surface golden test.
- **Performance** — scheduled ([.github/workflows/performance.yml](.github/workflows/performance.yml)),
  skips cleanly until endpoints exist; targets are provisional (ADR-006).
- **UAT** — release-candidate gate; 8 scenarios defined in
  [docs/UAT_PLAN.md](docs/UAT_PLAN.md), each automated + human sign-off.
The per-sprint matrix (which tests are written/grown/run each week) is in
TEST_STRATEGY.md section 8.

## Toolchain status (2026-08-24)

- **Installed & working:** `uv` 0.12.5 (user-space, `~/.local/bin`),
  **Python 3.12.14** (via uv, matches the pin), the full dev toolchain
  (`ruff`, `mypy`, `bandit`, `pytest`, `pre-commit`) in `.venv`, and
  **Docker 29.7.2 + Compose v5.5.0** (native Engine in WSL, systemd service;
  `dell` is in the `docker` group). `uv.lock` committed.
- **Verified green locally:** `ruff check` · `ruff format --check` ·
  `mypy --strict` (28 files) · `bandit` (0 issues) · `pytest --cov`
  (29 passed, 100% coverage). Run them with `uv run <tool>`.
- **Container path verified end-to-end:** `docker build` → `hip:local`
  (43 MB, amd64, non-root `appuser`); `docker run` imports the package and
  prints its module map; `docker compose up db` → Postgres reports **healthy**.
  (The first build caught a real bug — README.md wasn't copied into the build
  stage for hatchling; fixed.)

## Known gaps / prerequisites

- **Multi-arch build unverified.** Images build for `amd64` here; the
  `linux/arm64` half of the ADR-003 multi-arch target hasn't been built (needs
  `docker buildx` with QEMU or an arm runner) — CI is the place to prove it.
- **pre-commit + drvfs is slow.** The `gitleaks` hook scanning git history over
  `/mnt/d` (Windows-mounted) is prohibitively slow, so local commits use
  `--no-verify` after running the checks manually. gitleaks still runs in CI
  (secret-scan job). If local hooks are wanted, run them on the WSL-native side
  or keep gitleaks CI-only.
- No `LICENSE` file (private client repo — intentional unless told otherwise).

## Next recommended task

Pick one of: **Synthea bulk fixtures** (realistic-volume synthetic data for
demo/perf, replacing the hand-written ADT/ORU/ORM fixtures used so far),
**FHIR search for Encounter/Observation** (extend the blind-index pattern
already built for Patient), or **DiagnosticReport** (the HL7 OBR-25 mapping
deferred at the ADR-001 review). The self-hosted core is intentionally built
before the cloud-native variant (2026-08-25 deployment decision) — don't start
that until the items above are done.
