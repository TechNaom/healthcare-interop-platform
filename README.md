# Healthcare Interoperability Platform

A HIPAA-aligned HL7 v2 + FHIR (R4/R5) data integration platform. **Python-only for the current build** — orchestration, API surface, and validation/transform. C++ high-throughput validation is a documented future phase, not current scope (see [ADR-006](docs/DECISIONS.md#adr-006)). Containers as the deployable unit on any OS or cloud.

## Status: Kickoff questions resolved — 12-week AI-orchestrated track, Phase 0 starting

Every document below is written and internally consistent. Kickoff questions (track length, synthetic-data-only policy, GitHub remote) were resolved 2026-08-24 — see [Open Questions](<Healthcare Interop Platform.md#open-questions-from-kickoff-review>) for the record. Phase 0 (repo scaffold + canonical model spec) is next.

## Documentation map

| Doc | What's in it |
|---|---|
| [Healthcare Interop Platform.md](<Healthcare Interop Platform.md>) | Original SRS summary, phased roadmap (full-scope + 8-week/12-week AI-orchestrated tracks), hard constraints |
| [docs/SRS.md](docs/SRS.md) | Formal requirements — functional (FR-*), non-functional (NFR-*), external interfaces, assumptions |
| [docs/TECHNOLOGY_MAPPING.md](docs/TECHNOLOGY_MAPPING.md) | One-page answer to "for this requirement, what are we actually using" — every SRS section mapped to a concrete technology choice |
| [docs/TECH_STACK.md](docs/TECH_STACK.md) | The complete stack in one place, what to install locally, and what we deliberately don't use (no cloud, no Kubernetes for now) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component diagram, deployment view, technology stack, Python↔C++ boundary |
| [docs/DESIGN.md](docs/DESIGN.md) | Module breakdown, sequence diagrams, error handling, pluggable-infrastructure interfaces |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Canonical model entities and the HL7 v2 ↔ canonical ↔ FHIR field mapping |
| [docs/SECURITY_AND_COMPLIANCE.md](docs/SECURITY_AND_COMPLIANCE.md) | HIPAA technical-safeguards mapping, encryption, RBAC roles, de-identification, BAA policy |
| [docs/TEST_STRATEGY.md](docs/TEST_STRATEGY.md) | Where test data comes from (synthetic only), how it's loaded, test pyramid, compliance tests, environments |
| [docs/DECISIONS.md](docs/DECISIONS.md) | ADR log — the *why* behind every major choice |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | HL7/FHIR/HIPAA terms used throughout |

## Hard constraints (apply to every future change)

- **No real PHI, ever** — not in code, fixtures, logs, or this repo. Synthetic data only. (Reconfirmed 2026-08-24.)
- **No external CI/SaaS** without a signed BAA and explicit sign-off.
- **Platform-agnostic** — no OS-specific paths, no cloud-vendor SDK in core logic, containers always.

Full detail in [docs/SECURITY_AND_COMPLIANCE.md](docs/SECURITY_AND_COMPLIANCE.md) and [ADR-005](docs/DECISIONS.md#adr-005).

## For whoever picks this up

Read in this order: this README → `Healthcare Interop Platform.md` (roadmap/status) → `docs/SRS.md` → `docs/ARCHITECTURE.md` → `docs/DATA_MODEL.md` → `docs/DESIGN.md` → `docs/SECURITY_AND_COMPLIANCE.md`. `docs/DECISIONS.md` and `docs/GLOSSARY.md` are reference, read as needed.

Nothing here is speculative beyond what's marked "assumed" — every assumption is listed in [SRS §12](docs/SRS.md#12-constraints-and-assumptions) with its default and rationale, and every unresolved conflict is in [SRS §11](docs/SRS.md#11-open-items-and-conflicts--not-silently-resolved), so picking this up mid-flight means checking those two tables first, not re-deriving intent from code.
