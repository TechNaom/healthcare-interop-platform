# User Acceptance Test (UAT) plan

**Status:** Living plan. Scenarios are defined up front; each is automated in
`tests/uat/` and gated at the release-candidate stage, not per-PR.

UAT answers a different question from the other tiers. Unit/integration/
regression/performance ask *"is the code correct and fast?"*; UAT asks *"does
the system do what the people who depend on it need, through the interfaces they
actually use?"* Every scenario below is written from the perspective of an
integrating team (a sending EHR, a FHIR-consuming app, a compliance officer),
touches **only public interfaces**, and uses **synthetic data only** ([ADR-005](DECISIONS.md#adr-005)).

## How UAT runs

- Each scenario `UAT-NN` has a matching test in [`tests/uat/`](../tests/uat/)
  marked `uat`, excluded from the per-PR run and executed against a
  release-candidate stack.
- A scenario is **not** "done" until its test passes against synthetic data
  **and** a human acceptor has signed the row in the sign-off table.
- Scenarios stay in lockstep with the build: until the feature ships, its test
  `skip`s with the phase that unblocks it, so the UAT surface is visible from
  day one.

## Acceptance scenarios

| ID | As a… | Scenario | Acceptance criteria | Unblocked by |
|---|---|---|---|---|
| **UAT-01** | Sending EHR | Send an ADT^A01 over MLLP, then read the patient via FHIR | ACK returned; `GET /Patient/{id}` with a scoped token returns an R4 Patient whose fields match the source message | Phase 4–7 |
| **UAT-02** | Compliance officer | Confirm the de-identified store carries no PHI | For each of the 18 Safe Harbor categories, the de-identified copy contains no identifier | Phase 10 |
| **UAT-03** | FHIR-consuming app | CRUD + search core resources | Create/read/update/search on Patient, Encounter, Observation, Order behaves per FHIR R4; `OperationOutcome` on invalid input | Phase 6–7 |
| **UAT-04** | Ordering system | Send ORM/ORU, see order + results | ORM creates an Order; ORU attaches Observations; order status derivation matches [DATA_MODEL.md](DATA_MODEL.md#order-status-derivation) | Phase 4–7 |
| **UAT-05** | Security reviewer | Unauthorized/over-scoped access is refused | Missing/invalid token → 401; valid token lacking scope → 403; a role sees only its permitted fields (minimum-necessary) | Phase 9 |
| **UAT-06** | Operator | Malformed input degrades safely | Each malformed-message class yields a correct NACK / dead-letter entry, never a crash or silent accept | Phase 4–5 |
| **UAT-07** | Auditor | Every PHI access is recorded | Every read/write produces exactly one append-only audit entry; the entry identifies who/what/when | Phase 9 |
| **UAT-08** | Operator | The stack stands up from the delivered artifacts | `docker compose up` (or the Helm chart) brings the stack healthy; `/healthz` `/readyz` green; seed script loads synthetic fixtures through the real ingestion path | Phase 1, 5 |

## Sign-off (per release candidate)

| ID | Automated test passing | Human acceptor | Date | Notes |
|---|---|---|---|---|
| UAT-01 | ☐ | | | |
| UAT-02 | ☐ | | | |
| UAT-03 | ☐ | | | |
| UAT-04 | ☐ | | | |
| UAT-05 | ☐ | | | |
| UAT-06 | ☐ | | | |
| UAT-07 | ☐ | | | |
| UAT-08 | ☐ | | | |

A release candidate ships only when every applicable row is both checked and
signed. Scenarios whose phase hasn't been built yet are marked N/A for that
release, not skipped silently.
