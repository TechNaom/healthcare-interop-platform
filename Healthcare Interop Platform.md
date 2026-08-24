# Healthcare Interoperability Platform

A HIPAA-aligned HL7 v2 + FHIR (R4/R5) data integration platform. Python handles orchestration and the API surface; C++ handles high-throughput validation and transform; containers are the deployable unit on any OS or cloud.

| | |
|---|---|
| **Source** | SRS pasted in-chat, 2026-08-14 |
| **Plan status** | Draft — four scoping assumptions pending sign-off |
| **Consolidated from** | `IMPLEMENTATION_PLAN.md`, `ARCHITECTURE.md`, `ROADMAP_2MONTH.md`, `ROADMAP_3MONTH.md` |
| **Kickoff track decision** | Pending — see [Open Questions](#open-questions-from-kickoff-review) |
| **Scope amendment, 2026-08-24** | Python-only for the current build; C++ (Phase 4 below) is a future implementation pipeline, not scheduled now. Full detail in [docs/DECISIONS.md — ADR-006](docs/DECISIONS.md#adr-006). |

---

## Open decisions

The source SRS flagged these as unknown rather than leaving them to guesswork. The plan is built on platform-agnostic defaults so work isn't blocked — but **throughput** and **team size** are the two that move the schedule most if they change.

| Unknown | Default assumed | Why this default |
|---|---|---|
| Deployment target | Container-first (Docker/OCI), any Kubernetes distro or bare Compose on-prem | Matches the explicit platform-agnostic requirement |
| EHR vendors | Generic HL7 v2.x (ADT, ORM, ORU) + FHIR R4, no vendor quirks yet | Vendor-specific profiles (Epic, Cerner…) are painful and vendor-dependent — scoped as later hardening |
| Throughput targets | ~50 msg/s HL7, ~200 req/s FHIR, P95 < 300ms | Typical mid-size hospital integration-engine load; cheap to raise later since C++ scales out |
| Team size | 1–2 senior engineers (Python-leaning + C++-leaning), part-time security review | No team info given; timeline is sized for this and flagged where more people change it |

**If any default is wrong, say so and the plan gets re-cut** — throughput and team size shift the timeline the most of the four.

---

## System design

### Architecture

Four layers, each built platform-agnostic from the start rather than retrofitted later.

1. **Integration Gateway** — Python / FastAPI
   - FHIR R4/R5 REST APIs, admin endpoints
   - AuthN/AuthZ, throttling, request validation
2. **Messaging Engine**
   - Python: HL7 v2 parse / route / simple transform
   - C++: high-throughput FHIR/HL7 validation & transform, gRPC or pybind11 boundary to Python
3. **Data Persistence Layer**
   - PHI store — encrypted at rest, RBAC + field-level filtering
   - Immutable, append-only audit log store
   - De-identified store, kept separate, for analytics/AI
4. **Security & Compliance Services**
   - `KeyManager` / `SecretsProvider` / `ObjectStore` interfaces
   - Centralized audit logging, de-identification services

### Platform-agnostic standards, applied from phase 0

- **No OS-specific assumptions** — `pathlib` over raw paths in Python; C++ platform code isolated behind one `platform/` shim, not scattered `#ifdef`s.
- **Containers as the deployable unit** — multi-stage, multi-arch (`linux/amd64`, `linux/arm64`) builds verified in CI. Runs identically under Compose on-prem or any Kubernetes distribution.
- **Pluggable infrastructure, not hardcoded vendors** — `KeyManager` → self-hosted Vault by default; `ObjectStore` → MinIO/local FS by default; `MessageBus` → Kafka or RabbitMQ via config; DB access through an abstraction layer, Postgres as reference.
- **Confidential by default** — no telemetry, error reporting, or log sink points at third-party SaaS unless a BAA is signed and it's explicitly configured.

### Highest-leverage decision in the project

> HL7 v2 and FHIR both map to and from **one internal canonical data model**, rather than pairwise HL7↔FHIR translators.
>
> Get this reviewed before any ingestion or API code is written against it — retrofitting it after both paths exist is expensive.

### Language boundary: Python ↔ C++

Two supported paths, chosen per-service by measured need, not by default assumption:

- **gRPC (default)** — C++ services run as independent, horizontally scalable processes. Keeps the two languages' deployment lifecycles fully decoupled: C++ validators scale or redeploy without touching the Python gateway.
- **pybind11 (fallback)** — in-process native bindings, used only where gRPC round-trip latency is measured, not assumed, to be unacceptable. Couples the build to the C++ toolchain matching Python's deployment platform, so used sparingly.

---

## Implementation plan — full scope

Two timeline views: one engineer touching every layer in sequence, or two engineers running a Python/API track and a C++/services track side by side once the canonical model lands in Phase 1. Both assume ~40 focused hours/week per engineer.

| Ph. | Deliverable | Serial | Parallel |
|---|---|---|---|
| 0 | Foundations & governance | Wk 1–2 | Wk 1–2 |
| 1 | Core architecture & skeleton | Wk 3–5 | Wk 3–4 |
| 2 | HL7 v2 ingestion | Wk 6–9 | Wk 5–8 |
| 3 | FHIR API services | Wk 10–14 | Wk 5–9 |
| 4 | C++ high-performance services | Wk 15–19 | Wk 5–9 |
| 5 | Persistence & core security | Wk 20–23 | Wk 10–13 |
| 6 | HIPAA security controls | Wk 24–27 | Wk 14–17 |
| 7 | De-identification pipeline | Wk 28–30 | Wk 18–20 |
| 8 | Observability & reliability | Wk 31–33 | Wk 21–23 |
| 9 | Testing & compliance hardening | Wk 34–37 | Wk 24–27 |
| 10 | Documentation & handoff | Wk 38–39 | Wk 28–29 |

**Totals:** ~39 weeks (~9 months) serial with one engineer · ~29 weeks (~6.5 months) with two engineers running Python and C++ tracks in parallel from Phase 2 on.

Add 15–20% buffer for a real HIPAA environment (security review, pen-test remediation, legal sign-off on BAAs) — realistically **10–11 months serial / 7.5–8 months parallelized** to a compliant production launch, not counting external audit turnaround.

### Phase detail

| # | Phase | Weeks |
|---|---|---|
| 00 | Foundations & governance | 1–2 |
| 01 | Core architecture & skeleton | 3–5 |
| 02 | HL7 v2 ingestion | 6–9 |
| 03 | FHIR API services | 10–14 |
| 04 | C++ high-performance services | 15–19 |
| 05 | Persistence & core security | 20–23 |
| 06 | HIPAA security controls | 24–27 |
| 07 | De-identification pipeline | 28–30 |
| 08 | Observability & reliability | 31–33 |
| 09 | Testing & compliance hardening | 34–37 |
| 10 | Documentation & handoff | 38–39 |

---

## AI-orchestrated build — same end state, compressed

Both tracks compress the same scope from the full plan into a **functionally complete, demo/pilot-ready system** — not a HIPAA-audit-certified launch. Claude does the bulk of implementation; a human reviews and makes the calls that need one.

### 2-month track — 8 weeks, zero slack

| Week | Focus |
|---|---|
| 1 | Foundations + canonical model drafted & reviewed |
| 2 | FastAPI + C++ skeletons, gRPC stub between them |
| 3 | HL7 v2 ingestion: MLLP/HTTP/file-drop, parsing, routing, ACK/NACK |
| 4 | HL7→FHIR mapping, FHIR CRUD core resources |
| 5 | FHIR completeness, C++ validator wired in & benchmarked |
| 6 | Persistence, RBAC, audit log, KeyManager |
| 7 | Safe Harbor de-id, OpenTelemetry basics |
| 8 | Test suite, hardening, demo walkthrough |

### 3-month track — 12 weeks, built-in buffer

| Week | Focus |
|---|---|
| 1 | Foundations only |
| 2 | Canonical model gets its own week: drafted, revised, signed off |
| 3 | Skeletons + gRPC stub |
| 4–5 | HL7 ingestion built, then hardened against edge cases |
| 6 | HL7→FHIR mapping, FHIR CRUD core |
| 7 | FHIR completeness |
| 8 | C++ validator wired in & benchmarked |
| 9 | Persistence, RBAC, audit log, KeyManager |
| 10 | Safe Harbor de-id, OpenTelemetry |
| 11 | Integration testing + bug-fix buffer |
| 12 | Stabilization, demo, retrospective |

### What breaks the 8-week number

**Week 1's canonical data model.** Everything from week 3 onward builds against it — if that review drags past a few days, or gets revisited mid-build because a real EHR vendor quirk surfaces late, the slip ripples through every following week. The 12-week track exists specifically to give this decision, and one bad week elsewhere, somewhere to land.

### Out of scope for either track — and why more weeks wouldn't fix it

Not cut for being unimportant — cut because each is gated by something outside engineering throughput:

- **Full OAuth2/OIDC + SAML SSO federation** — needs a real institutional identity provider, usually a separate procurement conversation.
- **Third-party pen-testing and SAST/DAST audit cycles** — run on the vendor's calendar, and shouldn't touch real PHI without a signed BAA regardless.
- **NER-based unstructured-text de-identification** — Safe Harbor's structured-data rules ship on schedule; the NLP piece is its own future phase.
- **Multi-region/HA failover, message-bus decoupling** — matters at production scale, premature for a pilot.
- **Formal traceability matrix and incident-response runbook** — written once the system they describe is stable, not while it's still moving weekly.

---

## Next steps

1. Confirm or correct the four assumptions in the [Open Decisions](#open-decisions) table — this determines whether the 9-month or 6.5-month full-scope track applies.
2. Review and approve the canonical HL7↔FHIR data model before any ingestion or API code is written against it.
3. Decide gRPC vs. pybind11 as the default Python↔C++ boundary — both ship as stubs in Phase 1, but picking a default early avoids rework.
4. Once approved, start Phase 0 — repo/dev-env/CI scaffolding, CI kept self-hosted/local given the confidentiality requirement.

---

## Hard constraints

Carried into every future session on this project.

- **Confidential** — Private GitHub remote (`TechNaom/healthcare-interop-platform`) is the source of truth as of 2026-08-24. No external CI/SaaS (scanners, telemetry, error reporting) without explicit sign-off.
- **Platform-agnostic** — No OS-specific code paths, no cloud-vendor SDK hardcoded into core logic. Containers as the deployment unit, always.
- **PHI handling** — Anything touching real patient data needs a BAA in place before it goes near a third-party service, including AI code review tools, SaaS linters, and cloud NLP APIs. Default to self-hosted equivalents. **All development and test fixtures use synthetic data only — no real PHI enters this repo or this chat.**

---

## Open questions from kickoff review

Raised 2026-08-24, answered 2026-08-24.

1. **Track: 8-week or 12-week?** → **12-week track** chosen — built-in buffer for the canonical model review and one bad week elsewhere.
2. **Synthetic data only, confirmed?** → **Confirmed.** No real patient data enters this repo, test fixtures, sample HL7 messages, or chat at any point.
3. **Is anything beyond this document itself confidential?** → Superseded by the git-remote question below; no other confidential material flagged.

**Resolved separately:** the repo is now hosted on a private GitHub remote (`TechNaom/healthcare-interop-platform`), superseding the earlier "no git remote, local-only" constraint — see updated Hard constraints above.

**Next up:** repo scaffold (containers, multi-arch CI config kept local, pre-commit hooks, `platform/` shim layout) plus a written canonical model spec covering **Patient, Encounter, Observation, Order** — the four resources that carry ADT/ORM/ORU — with HL7 v2 ↔ canonical ↔ FHIR R4 mappings laid out for review before any parser exists (Week 1–2 of the 12-week track).
