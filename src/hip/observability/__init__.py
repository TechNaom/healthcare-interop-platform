"""Observability — structured logging (and, later, OpenTelemetry metrics/traces).

The overriding constraint here is HIPAA-specific: **no PHI in logs**
(docs/TEST_STRATEGY.md 4, SRS 7.3). Logs carry control-plane facts only
(message outcome, stage, message-control-id, sending system) — never patient
content. Structured JSON output makes that auditable and machine-parseable.
"""
