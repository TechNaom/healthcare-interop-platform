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

---

## ADR-007: GitHub Actions for CI, on the private repo

**Status:** Accepted, 2026-08-24

**Context:** The original SRS default was self-hosted/local CI, driven by the "no external CI/SaaS without sign-off" confidentiality constraint. Source control itself was later moved to a private GitHub repo ([ADR-004](#adr-004)), which already accepted GitHub as a trusted party for code storage. The remaining question was whether CI execution should extend that same trust (GitHub-hosted runners) or stay stricter (self-hosted runner, code never executes on GitHub-owned infrastructure).

**Decision:** Use GitHub Actions on GitHub-hosted runners for this private repo's CI (build, test, lint/static analysis per [SRS §10.3](SRS.md#10-implementation-and-testing-requirements)).

**Consequences:** No extra infrastructure to stand up or maintain. CI logs and build output live on GitHub's infrastructure during runs, same trust boundary already accepted for source storage. The synthetic-data-only rule ([ADR-005](#adr-005)) is what makes this safe — CI never has real PHI to leak in the first place, so the added exposure from GitHub-hosted runners is minimal. If real PHI processing ever needs to run through CI (e.g. a future compliance-hardening phase), revisit this decision before that happens — it would need a signed BAA with GitHub or a move to a self-hosted runner, not an assumption that this ADR still applies.

---

## ADR-008: Self-hosted Keycloak for identity, from day one

**Status:** Accepted, 2026-08-24

**Context:** [SRS §5.1](SRS.md#51-access-control) requires token-based auth (OAuth 2.0/OIDC), RBAC combined with ABAC, and automatic logoff/session expiry. [SRS §4.2.5](SRS.md#42-fhir-api-services-python) additionally raises SMART-on-FHIR scopes if a consuming app needs them. Full institutional SSO/SAML federation remains an open item ([SRS §11](SRS.md#11-open-items-and-conflicts--not-silently-resolved)) — the original roadmap scoped it out as needing a separate procurement conversation.

An earlier draft proposed issuing and validating JWTs directly in the Gateway (`PyJWT`/`python-jose`) as the simpler pilot option, deferring any identity server.

**Decision:** Use **self-hosted Keycloak** as the identity provider from the start, rather than hand-rolling JWT issuance in the Gateway.

**Rationale:** "Just issue JWTs" understates the actual surface. Meeting the requirements above by hand means building and owning token lifecycle, refresh, revocation, signing-key rotation, and session expiry — security-critical code that must later be defended to an auditor. Keycloak provides all of it as configuration, is self-hostable (so no BAA question, consistent with [ADR-003](#adr-003) and the no-SaaS-without-BAA rule), and speaks **both** OIDC and SAML. That last point converts the open SSO/SAML item from a potential rewrite into a realm configuration change.

**Consequences:**
- One more container in the Compose stack and a real component to configure — the honest cost of this decision.
- RBAC/ABAC enforcement still lives in `gateway.auth` ([DESIGN.md §1](DESIGN.md#1-module-breakdown)); Keycloak supplies identity and tokens, it does not become the authorization logic. The Gateway remains the single enforcement point.
- If SSO/SAML federation is later confirmed in scope, it is a Keycloak identity-brokering configuration rather than an auth rewrite.
- Revisit only if a concrete constraint makes running Keycloak impossible in the target environment — not for perceived simplicity.

---

## ADR-009: Audit-log anomaly detection is self-hosted, and out of initial scope

**Status:** Accepted, 2026-08-24

**Context:** The client-provided SRS lists "Cyber security AI" under audit controls ([SRS §5.4](SRS.md#54-audit-logging)). It was left deliberately unresolved as an open item, since the phrasing did not distinguish a self-hosted component from a third-party service.

**Decision:** Any AI/anomaly-detection capability over the audit log will be a **self-hosted component** operating on the audit store inside the platform's own infrastructure. No third-party "security AI" service is adopted. The capability itself is **deferred out of the initial build** and is not required for HIPAA compliance.

**Rationale:** HIPAA §164.312(b) requires audit *controls* — recording and enabling examination of ePHI access. That obligation is met by the append-only audit log ([SRS §5.4](SRS.md#54-audit-logging)), not by an AI layer on top of it. Shipping audit metadata (which identifies who accessed which patient record and when — sensitive in its own right) to an external vendor would require a signed BAA and create an ongoing third-party exposure, in exchange for a capability that is an enhancement rather than a requirement.

**Consequences:**
- The audit log schema must be queryable enough to support later analysis — a design consideration for the persistence layer now, even though the analysis component is not built.
- When scheduled, a first implementation is a scheduled Python job over the audit table detecting: access-count outliers per user, access at unusual hours, and access to patient records with no related encounter. No external dependency, no BAA.
- If the client later insists on a specific third-party product, this ADR is superseded — and a signed BAA is a precondition, not a follow-up.
