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

| Level | Scope | Runs against | Speed |
|---|---|---|---|
| **Unit** | One module — parsers, mappers, de-id rules, RBAC decisions | In-process, no I/O | Milliseconds |
| **Integration** | Two or more components — ingestion → canonical → persistence | Real Postgres + Keycloak in containers | Seconds |
| **End-to-end** | Full stack, real transports | Complete Compose stack | Minutes |
| **Load** | Throughput/latency vs. [SRS §7.1](SRS.md#71-performance-and-scalability) targets | Full stack, generated volume | Long-running, not per-commit |

Integration and E2E use **real containerized dependencies** (Postgres, Keycloak, Vault, MinIO) rather than mocks. Mocking a database hides exactly the class of bug — transaction boundaries, constraint violations, permission enforcement — that matters most here. [Testcontainers](https://testcontainers.com/) manages container lifecycle from within the test run.

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

## 8. Open questions

1. **Load-test target environment** — [SRS §7.1](SRS.md#71-performance-and-scalability) throughput figures are provisional for a Python-only build ([ADR-006](DECISIONS.md#adr-006)). Benchmarking on a developer laptop won't predict production; a representative host is needed before those numbers mean anything.
2. **Client pilot data** — whether the pilot runs on synthetic data (no BAA needed, and sufficient to demonstrate the system) or real PHI (BAA + risk assessment first). Worth settling early, since it determines whether the pilot is an engineering milestone or a compliance project.
