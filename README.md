# Healthcare Interoperability Platform

A HIPAA-aligned HL7 v2 + FHIR (R4/R5) data integration platform. Python for orchestration and the API surface, C++ for high-throughput validation and transform, containers as the deployable unit on any OS or cloud.

## Status: Planning complete — build not started

Every document below is written and internally consistent. No source code exists in this repository yet, by design — implementation starts only on explicit go-ahead. See [Open Questions](<Healthcare Interop Platform.md#open-questions-from-kickoff-review>) for the two things still pending your confirmation before Phase 0 begins.

## Documentation map

| Doc | What's in it |
|---|---|
| [Healthcare Interop Platform.md](<Healthcare Interop Platform.md>) | Original SRS summary, phased roadmap (full-scope + 8-week/12-week AI-orchestrated tracks), hard constraints |
| [docs/SRS.md](docs/SRS.md) | Formal requirements — functional (FR-*), non-functional (NFR-*), external interfaces, assumptions |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component diagram, deployment view, technology stack, Python↔C++ boundary |
| [docs/DESIGN.md](docs/DESIGN.md) | Module breakdown, sequence diagrams, error handling, pluggable-infrastructure interfaces |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Canonical model entities and the HL7 v2 ↔ canonical ↔ FHIR field mapping |
| [docs/SECURITY_AND_COMPLIANCE.md](docs/SECURITY_AND_COMPLIANCE.md) | HIPAA technical-safeguards mapping, encryption, RBAC roles, de-identification, BAA policy |
| [docs/DECISIONS.md](docs/DECISIONS.md) | ADR log — the *why* behind every major choice |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | HL7/FHIR/HIPAA terms used throughout |

## Hard constraints (apply to every future change)

- **No real PHI, ever** — not in code, fixtures, logs, or this repo. Synthetic data only.
- **No external CI/SaaS** without a signed BAA and explicit sign-off.
- **Platform-agnostic** — no OS-specific paths, no cloud-vendor SDK in core logic, containers always.

Full detail in [docs/SECURITY_AND_COMPLIANCE.md](docs/SECURITY_AND_COMPLIANCE.md) and [ADR-005](docs/DECISIONS.md#adr-005).

## For whoever picks this up

Read in this order: this README → `Healthcare Interop Platform.md` (roadmap/status) → `docs/SRS.md` → `docs/ARCHITECTURE.md` → `docs/DATA_MODEL.md` → `docs/DESIGN.md` → `docs/SECURITY_AND_COMPLIANCE.md`. `docs/DECISIONS.md` and `docs/GLOSSARY.md` are reference, read as needed.

Nothing here is speculative beyond what's marked "assumed" — every assumption is listed in [SRS §9](docs/SRS.md#9-constraints--assumptions) with its default and rationale, so picking this up mid-flight means checking that table first, not re-deriving intent from code.
