# Test strategy

**Status:** Draft for review — planning only, no test code exists yet.

Expands [SRS §10](SRS.md#10-implementation-and-testing-requirements). The governing constraint is [ADR-005](DECISIONS.md#adr-005): **no real PHI, ever** — not in fixtures, not in a "just this once" debugging session, not in CI logs. Everything below follows from that.

## 1. Test data — where it comes from

Three tiers, each solving a problem the others can't.

### Tier 1 — Synthea (bulk realistic data)

[Synthea](https://github.com/synthetichealth/synthea) (MITRE, Apache-2.0) generates synthetic patient populations with coherent longitudinal medical histories — a patient's diabetes diagnosis is followed by consistent medications, encounters, and lab results over simulated years. It exports **FHIR R4 bundles** and **HL7 v2 messages** directly, which is exactly this project's two edges.

Why this rather than writing our own generator: realistic *distributions* and internally consistent histories are hard to fake by hand, and unrealistic data hides bugs — every patient having exactly one encounter never exercises the code paths that break in production.

**How it's used:**
- Run Synthea once per data refresh, not per test run (generation is slow).
- Commit a **small curated subset** (~20–50 patients) to the repo as the standard fixture set — enough for integration tests, small enough to review and keep the repo sane.
- Generate larger populations (1k–100k patients) on demand into a gitignored directory for load testing.
- A `Makefile`/CLI target regenerates the curated set reproducibly (fixed seed) so fixtures aren't mystery artifacts.

### Tier 2 — Hand-crafted edge cases

Synthea produces *valid, well-formed* data. Integration engines break on the opposite. These fixtures are written deliberately, one file per scenario, each named for what it tests:

| Category | Examples |
|---|---|
| Malformed structure | Truncated message, missing `MSH`, wrong segment order, unterminated segment |
| Encoding | Non-ASCII names, alternate delimiters declared in MSH-2, escaped delimiters in field values |
| Missing required fields | No PID-3, no MSH-10, empty OBX-5 with a non-empty OBX-2 |
| Unmapped values | An OBX-2 data type outside our mapping table, an unknown PV1-2 patient class |
| Boundary conditions | Age > 89 (Safe Harbor cap), far-future dates, a 200-repetition OBX group |
| Vendor variation | Encounter identity in PID-18 instead of PV1-19 ([DATA_MODEL.md](DATA_MODEL.md#encounter-identity-a-real-vendor-variation)); undocumented Z-segments |
| Ordering semantics | ORC-1 cancel with ORC-5 absent, and with ORC-5 present — the conditional in [DATA_MODEL.md](DATA_MODEL.md#order-status-derivation) |

Each of these should produce a **specific, correct failure** (a NACK with the right reason code, a dead-letter entry) — not a crash, and not silent acceptance.

### Tier 3 — Test-time factories

Python builder functions (`make_patient(birth_date=None)`) for unit tests, so a test needing one specific malformed shape doesn't require a committed file. Keeps unit tests readable and fixtures uncluttered.

### What is never used

Real patient data, de-identified real patient data, or "anonymized" exports from a client system. De-identification is itself a thing under test here — using its output as test input is circular, and re-identification risk on real data is never zero. See [ADR-005](DECISIONS.md#adr-005).

## 2. How data gets loaded

**Through the real ingestion path, never a back-door database insert.**

A seeding CLI (`scripts/seed.py`) reads fixtures and drives them through the actual transports — MLLP socket, HTTP POST, or file-drop directory. Seeding by inserting rows directly into Postgres would produce database state that the ingestion pipeline never validated, meaning tests pass against data the real system could never have produced.

```
seed.py --fixtures fixtures/curated/ --transport mllp --host localhost --port 2575
```

Consequences worth noting: seeding is slower this way, and it *can fail* — which is the point. A fixture that won't load is either a broken fixture or a real ingestion bug, and both are worth knowing about.

## 3. Test pyramid

| Level | Scope | Runs against | Speed | Marker |
|---|---|---|---|---|
| **Unit** | One module — parsers, mappers, de-id rules, RBAC decisions | In-process, no I/O | Milliseconds | `unit` |
| **Integration** | Two or more components — ingestion → canonical → persistence | Real Postgres + Keycloak in containers | Seconds | `integration` |
| **End-to-end** | Full stack, real transports | Complete Compose stack | Minutes | `e2e` |
| **Regression** | Locks previously-shipped behavior against silent change | In-process + golden files | Fast | `regression` |
| **Performance** | Throughput/latency vs. [SRS §7.1](SRS.md#71-performance-and-scalability) targets | Full stack, generated volume | Long-running, not per-commit | `performance` |
| **UAT** | Acceptance scenarios through public interfaces ([UAT_PLAN.md](UAT_PLAN.md)) | Release-candidate stack | Minutes | `uat` |

Integration and E2E use **real containerized dependencies** (Postgres, Keycloak, Vault, MinIO) rather than mocks. Mocking a database hides exactly the class of bug — transaction boundaries, constraint violations, permission enforcement — that matters most here. [Testcontainers](https://testcontainers.com/) manages container lifecycle from within the test run.

Tests live under `tests/<tier>/` and carry the marker above (registered in `pyproject.toml`, enforced by `--strict-markers`). Selection is by marker, so the same suite serves the per-PR gate and the scheduled/release gates:

```
uv run pytest -m "not performance and not uat"   # per-PR (unit, integration, e2e, regression, compliance)
uv run pytest -m performance                       # scheduled perf job
uv run pytest -m uat                               # release-candidate UAT
```

### Regression tier

Every behavior we ship gets a lock so it can't change silently. The first, live from Phase 0, is a **module-surface golden test** (`tests/regression/test_module_surface.py`) that fails if a public `hip` module vanishes without the golden file being updated in the same change. As real behavior lands, regression grows **golden-output** tests: a fixed input (a specific HL7 message, a canonical record) is mapped/serialized and compared byte-for-byte against a reviewed expected output, so an unintended change to a mapping or FHIR shape fails in review rather than in production. Golden files are updated **deliberately** (a reviewed diff), never blindly.

### UAT tier

User-acceptance scenarios are defined up front in [UAT_PLAN.md](UAT_PLAN.md) (UAT-01…UAT-08), each automated in `tests/uat/` and each requiring a human sign-off in addition to a passing test. UAT is a **release-candidate gate**, not a per-PR check, and runs only on synthetic data.

### The end-to-end test that matters most

The full round trip, which exercises nearly every requirement in one path:

```
HL7 v2 ADT over MLLP
  → parsed and validated
  → mapped to canonical model
  → persisted to PHI store (encrypted)
  → audit entry written
  → de-identification produces a de-identified copy
  → FHIR GET /Patient/{id} with a scoped token
  → returned resource matches expected FHIR R4 shape
  → audit entry written for the read
  → de-identified store contains no Safe Harbor identifiers
```

Every arrow is a requirement. If this test passes for ADT, ORM, and ORU, the system does what it claims.

## 4. Compliance tests — unusual to this project

These aren't standard application tests; they verify claims made to auditors. They are the tests most worth writing carefully.

| Test | Asserts |
|---|---|
| **Audit completeness** | Every PHI read/write produces **exactly one** audit entry — not zero (missed), not two (double-logged). Run by comparing an operation counter against audit-table rows across a scripted workload. |
| **Audit immutability** | `UPDATE` and `DELETE` against the audit table **fail** for the application role. Asserts the DB-level grant, not just that application code doesn't try. |
| **De-identification completeness** | For every Safe Harbor category, generate a record containing that identifier, run de-identification, assert it is absent from the output. 18 categories, 18 assertions minimum. |
| **Minimum-necessary enforcement** | For each role, request a resource and assert the response contains **only** the fields that role may see — including negative assertions that restricted fields are absent, not merely blank. |
| **No-PHI-in-logs** | Run a workload, scan all emitted logs/traces for known fixture PHI values (names, MRNs, birth dates from fixtures). Any hit fails the build. Directly enforces [SRS §7.3](SRS.md#73-observability). |
| **Store separation** | Assert no code path and no DB grant permits the analytics role to reach the PHI store, and that no reverse path exists from de-identified back to PHI. |
| **Encryption at rest** | Verify PHI is unreadable in the raw data files/volume, not merely that the config flag is set. |

The **no-PHI-in-logs** test is only possible because fixtures are synthetic and their values are known — a useful side effect of the constraint.

## 5. Environments

| Environment | What it is | Data |
|---|---|---|
| **Local dev** | Full Compose stack on a developer machine | Curated Synthea subset + edge cases |
| **CI** | Ephemeral containers per run, GitHub Actions ([ADR-007](DECISIONS.md#adr-007)) | Same fixtures, committed to the repo |
| **Load** | Compose stack, more resources | Large generated Synthea population, gitignored |
| **Client pilot** | Client-controlled infrastructure | **Client's decision.** If real PHI is involved, a BAA and a HIPAA Security Risk Assessment come first — out of scope for this build, and not something this test strategy covers. |

There is deliberately **no shared staging environment with real data**. That pattern is where PHI leaks in most healthcare projects.

## 6. Tooling

| Purpose | Tool |
|---|---|
| Test runner | `pytest` |
| Container lifecycle in tests | `testcontainers` |
| HTTP client for API tests | `httpx` (async, matches FastAPI) |
| Property-based testing | `hypothesis` — valuable for parser edge cases; generates malformed inputs we wouldn't think to write |
| Load testing | `locust` (Python, matches the stack) |
| Coverage | `pytest-cov` |
| Static/security analysis | `ruff`, `mypy`, `bandit` — CI gates, per [SRS §10.3](SRS.md#10-implementation-and-testing-requirements) |

## 7. What "done" means per phase

Each phase ends with tests proving the requirements it claims, not just working code:

| Phase | Test gate |
|---|---|
| Canonical model | Round-trip property test: HL7 → canonical → FHIR → canonical is stable; mapping table matches [DATA_MODEL.md](DATA_MODEL.md) field-for-field |
| HL7 ingestion | All Tier-2 edge cases produce correct NACK/dead-letter outcomes; no crash on any malformed input |
| FHIR API | CRUD + search per resource; ETag/If-Match concurrency; `OperationOutcome` on validation failure |
| Persistence & security | Full compliance-test suite (§4) passing |
| De-identification | All 18 Safe Harbor categories verified absent |
| Observability | No-PHI-in-logs test passing under a full workload |

## 8. Testing at every sprint — cadence matrix

Testing is not a phase; it runs **every sprint**. The four types the client asked
for map onto the 12-week track as follows. "New" = write tests for this sprint's
feature; "Grow" = extend the golden/scenario set; "Run" = execute an existing
suite as a gate. Unit + regression run on **every PR**; performance is
**scheduled**; UAT is a **release-candidate** gate that also gets a rehearsal at
mid-point and demo.

| Sprint (wk) | Focus | Unit | Regression | Performance | UAT |
|---|---|---|---|---|---|
| 1 — Foundations | scaffold, CI, tiers | Structure/import smoke (live) | Module-surface golden (live) | Harness + locust skeleton wired | Plan authored ([UAT_PLAN.md](UAT_PLAN.md)); tests stubbed |
| 2 — Canonical model | mapping tables | **New**: field-map + round-trip property tests | **Grow**: golden canonical records | — (no runtime yet) | UAT-01/03/04 criteria pinned to mappings |
| 3 — Skeletons | FastAPI app, health | **New**: app factory, `/healthz` `/readyz` | **Grow**: health contract golden | **Run**: baseline latency on health | UAT-08 (stack stands up) first pass |
| 4–5 — HL7 ingestion | MLLP/parse/route/ACK | **New**: parser, router, ACK/NACK per edge case | **Grow**: golden NACK reasons per malformed class | **Run**: ingest throughput vs ~50 msg/s | UAT-06 (safe degradation) automated |
| 6 — HL7→FHIR + CRUD | mapper + FHIR core | **New**: mapper, CRUD handlers | **Grow**: golden FHIR resource shapes | **Run**: FHIR read/write P95 < 300ms | UAT-01/03/04 executable |
| 7 — FHIR completeness | search, concurrency | **New**: search params, ETag/If-Match | **Grow**: search-result goldens | **Run**: ~200 req/s FHIR sustained | UAT-03 full |
| 8 — Validator hardening | validation/transform | **New**: terminology/structural cases | **Grow**: validation-outcome goldens | **Run**: validation overhead measured | — |
| 9 — Persistence & security | RBAC, audit, keys | **New**: RBAC decisions, repo logic; **compliance** suite (§4) | **Grow**: audit-shape goldens | **Run**: write path under load | UAT-05/07 automated |
| 10 — De-id + observability | Safe Harbor, OTel | **New**: 18-category de-id, no-PHI-in-logs | **Grow**: de-id output goldens | **Run**: de-id pipeline throughput | UAT-02 automated |
| 11 — Integration + buffer | end-to-end | Fill gaps | **Full regression run** | **Full load run** on a representative host | Full UAT dry run + fixes |
| 12 — Stabilization | demo, retro | Green everywhere | **Release regression gate** | **Release perf sign-off** vs SRS §7.1 | **Release UAT sign-off** (human + automated) |

**Gates, concretely:**
- **Every PR** — `pytest -m "not performance and not uat"` (unit, integration, e2e, regression, compliance) + ruff + mypy + bandit + gitleaks must pass. Coverage tracked, not yet ratcheted while stubs dominate.
- **Nightly / scheduled** — `pytest -m performance` against a running stack; perf numbers are **provisional for the Python-only build** ([ADR-006](DECISIONS.md#adr-006)) and re-benchmarked, not assumed. See [performance workflow](../.github/workflows/performance.yml).
- **Release candidate** — full suite including `-m uat`, plus the human sign-off table in [UAT_PLAN.md](UAT_PLAN.md). A candidate ships only when every applicable UAT row is checked **and** signed.

## 9. Open questions

1. **Load-test target environment** — [SRS §7.1](SRS.md#71-performance-and-scalability) throughput figures are provisional for a Python-only build ([ADR-006](DECISIONS.md#adr-006)). Benchmarking on a developer laptop won't predict production; a representative host is needed before those numbers mean anything.
2. **Client pilot data** — whether the pilot runs on synthetic data (no BAA needed, and sufficient to demonstrate the system) or real PHI (BAA + risk assessment first). Worth settling early, since it determines whether the pilot is an engineering milestone or a compliance project.
