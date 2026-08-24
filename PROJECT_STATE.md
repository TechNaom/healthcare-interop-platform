# Project State

_Living status doc. Update at the end of every meaningful work session._
_Last updated: 2026-08-24._

## What this is

A HIPAA-aligned HL7 v2 + FHIR (R4/R5) interoperability platform. Python-only
for the current build (C++ high-throughput validation is a documented future
phase — [ADR-006](docs/DECISIONS.md#adr-006)). Containers are the deployment
unit. Full context: [README.md](README.md) → [Healthcare Interop Platform.md](<Healthcare Interop Platform.md>)
→ `docs/`.

## Current status

**Phase 0 (Foundations & governance) — scaffolding in progress on branch `phase-0-scaffold`.**

- Planning: **complete.** SRS, architecture, design, data model,
  security/compliance, test strategy, tech stack, and 9 ADRs are all written
  and internally consistent (`docs/`).
- Kickoff questions: **resolved** 2026-08-24 — 12-week AI-orchestrated track;
  synthetic-data-only reconfirmed; private GitHub remote is the source of
  truth (supersedes the original "local-only" default, per [ADR-004](docs/DECISIONS.md#adr-004)).
- Code: **repo skeleton being laid down** — package tree, interface stubs,
  container/CI/pre-commit config. **No business logic yet** — every module is a
  documented stub pointing at its design-doc section.

## Timeline — 12-week AI-orchestrated track

| Week | Focus | State |
|---|---|---|
| 1 | Foundations only | 🔨 in progress |
| 2 | Canonical model: drafted, revised, signed off | ⬜ |
| 3 | Skeletons (gRPC stub deferred — ADR-006) | ⬜ |
| 4–5 | HL7 ingestion built, then hardened | ⬜ |
| 6 | HL7→FHIR mapping, FHIR CRUD core | ⬜ |
| 7 | FHIR completeness | ⬜ |
| 8 | Python validator hardening (C++ deferred — ADR-006) | ⬜ |
| 9 | Persistence, RBAC, audit log, KeyManager | ⬜ |
| 10 | Safe Harbor de-id, OpenTelemetry | ⬜ |
| 11 | Integration testing + bug-fix buffer | ⬜ |
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
tests/          test_scaffold.py (import/health smoke tests)
```

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

**Week 2:** write the canonical data model spec deliverable
(Patient / Encounter / Observation / Order) building on
[docs/DATA_MODEL.md](docs/DATA_MODEL.md), and get it reviewed **before** any
`messaging.canonical.mapper` or parser code is written against it (ADR-001).
Then wire the FastAPI app factory + `/healthz` / `/readyz` (first real code in
`hip.gateway`).
