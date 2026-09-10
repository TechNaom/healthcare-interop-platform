-- Least-privilege grants for the application role (docs/DATA_MODEL.md, SRS 5.4).
--
-- Migrations run as the schema owner; the APPLICATION connects as a restricted
-- role so two HIPAA guarantees are enforced by the database, not just by code:
--
--   1. Audit immutability (164.312(b)) — the app can INSERT audit rows but
--      cannot UPDATE or DELETE them. Same for the dead-letter store.
--   2. Store separation — analytics/de-id consumers can read the de-identified
--      store but have NO access to the PHI store (no reverse path).
--
-- Apply as the owner after migrations. Ops sets a password / connection method
-- (or cloud IAM auth) out of band; point HIP_DATABASE_URL at hip_app.
-- The integration compliance tests assert these grants actually hold.

-- Application role: normal CRUD on mutable stores, append-only on the ledgers.
CREATE ROLE hip_app NOLOGIN;
GRANT USAGE ON SCHEMA public TO hip_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON phi_resources        TO hip_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON deid_resources       TO hip_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON phi_identifier_index TO hip_app;

-- Append-only: insert + read, but never mutate or remove.
GRANT SELECT, INSERT ON audit_events        TO hip_app;
GRANT SELECT, INSERT ON dead_letter_messages TO hip_app;
-- (No UPDATE/DELETE granted on the two ledgers — that is the immutability control.)

-- Analytics role: de-identified store only. No PHI, no audit, no dead-letter.
CREATE ROLE hip_analytics NOLOGIN;
GRANT USAGE ON SCHEMA public TO hip_analytics;
GRANT SELECT ON deid_resources TO hip_analytics;
