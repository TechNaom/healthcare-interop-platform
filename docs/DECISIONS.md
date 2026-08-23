# Architecture decision records

Short-form ADRs — Status / Context / Decision / Consequences. New decisions get appended, never rewritten in place; if a decision is reversed, add a new ADR that supersedes it and mark the old one's status accordingly.

---

## ADR-001: Canonical data model over pairwise HL7↔FHIR translators

**Status:** Accepted

**Context:** The platform must convert between HL7 v2 and FHIR R4/R5 in both directions. Writing direct HL7→FHIR and FHIR→HL7 translators is faster to start but scales as N×M with every added message type, FHIR version, or vendor quirk.

**Decision:** Both HL7 v2 and FHIR map to and from one internal canonical model. All ingestion and API code is written against the canonical model, never directly against the other wire format.

**Consequences:** One extra mapping layer to design up front — this is the reason the canonical model gets its own reviewed deliverable before any ingestion/API code exists ([DATA_MODEL.md](DATA_MODEL.md)). In exchange, adding a new FHIR version, message type, or (later) vendor profile touches one mapping table instead of every pairwise translator.

---

## ADR-002: gRPC as default Python↔C++ boundary, pybind11 as measured fallback

**Status:** Deferred — see [ADR-006](#adr-006). This decision still stands for whenever the C++ phase begins; it does not apply to the current Python-only build.

**Context:** Python owns orchestration/API surface; C++ owns high-throughput validation/transform. They need a boundary. gRPC keeps them as independent, separately-scalable processes; pybind11 gives lower latency but couples deployment/build lifecycles.

**Decision:** Default every service pair to gRPC. Only switch a specific service to pybind11 if measured round-trip latency under real load is unacceptable — not assumed unacceptable.

**Consequences:** Slightly higher baseline latency than in-process calls, accepted for full deploy/scale independence. Revisit per-service in Phase 4 once real benchmarks exist.

---

## ADR-003: Container-first, platform-agnostic deployment

**Status:** Accepted

**Context:** Deployment target (client's own K8s, a specific cloud, on-prem Compose) was unknown at planning time.

**Decision:** Every service ships as a multi-stage, multi-arch (`linux/amd64`, `linux/arm64`) OCI image, runnable identically under Compose or any Kubernetes distribution. No core logic imports a cloud-vendor SDK directly.

**Consequences:** Some cloud-native conveniences (e.g., a specific cloud's managed KMS) are deliberately not used directly — infrastructure dependencies go through the interfaces in [DESIGN.md §5](DESIGN.md#5-pluggable-infrastructure--interface-shapes) instead, with a self-hosted reference implementation for each.

---

## ADR-004: Private GitHub repo, no external CI/SaaS without sign-off

**Status:** Accepted, 2026-08-24

**Context:** The source SRS's default was "no git remote, local-only." The client (repo owner) explicitly requested a private GitHub repo for ease of handover.

**Decision:** Source lives in a private GitHub repo (`TechNaom/healthcare-interop-platform`), no collaborators added beyond the owner, no external CI/SaaS wired in without separate explicit sign-off. This is treated as the explicit override the original constraint required — not a silent default change.

**Consequences:** Handover is simpler (standard `git clone` access instead of a manual file transfer). The "no real PHI in the repo" rule stays absolute regardless — see [ADR-005](#adr-005) — a private repo is not a PHI-handling control.

---

## ADR-005: Synthetic-data-only policy

**Status:** Accepted

**Context:** Any real PHI touching a third-party service (including AI coding tools, this one included) needs a signed BAA first. No BAA exists for this engagement at planning time.

**Decision:** No real patient data enters this repository, any test fixture, any chat session, or any log at any point in this engagement, without exception. All development, demo, and test data is synthetic.

**Consequences:** Some edge cases that only show up with messy real-world data (vendor quirks, malformed real messages) won't surface until a later phase explicitly scoped for that, with a BAA in place first. This is treated as acceptable — see roadmap's "out of scope" rationale for vendor-specific hardening.

---

## ADR-006: Python-only for initial build; C++ deferred to a future phase

**Status:** Accepted, 2026-08-24

**Context:** The original SRS specified Python for orchestration/API and C++ for high-throughput validation/transform, connected via gRPC ([ADR-002](#adr-002)). The client revised scope: build Python-only for now; C++ is a future implementation pipeline, not part of the current build.

**Decision:** The Messaging Engine's validation/transform responsibility is implemented entirely in Python for the initial build. The architecture keeps that responsibility in its own module/service boundary (not entangled with routing or the FHIR API layer) specifically so a C++ implementation can be swapped in later behind the same gRPC contract from [ADR-002](#adr-002) without a redesign — the seam is designed in from the start even though the C++ side of it isn't built now.

**Consequences:**
- Throughput targets (~50 msg/s HL7, ~200 req/s FHIR, P95 < 300ms) were sized assuming a C++ validator. They are **provisional** for the Python-only build and should be re-benchmarked against the actual Python implementation rather than assumed — see [SRS §7.1](SRS.md#71-performance-and-scalability).
- The roadmap's Phase 4 ("C++ high-performance services") moves from "later hardening" to "future phase, not currently scheduled" — it stays in the plan as a documented future pipeline, not deleted.
- [ADR-002](#adr-002) (gRPC default, pybind11 fallback) is not reversed, only deferred — it's the design to reach for when/if the C++ phase actually starts.
