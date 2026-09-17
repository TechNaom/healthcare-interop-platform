"""Minimum-necessary field filtering (HIPAA 164.502(b), SRS 5.1 ABAC).

Beyond RBAC (can this caller read this resource type at all), the minimum-
necessary rule limits *which fields* a caller sees to what their role needs.
Full clinical access requires the ``phi:full`` role; without it, a caller gets a
reduced view — enough to identify/match a record, not the clinical detail.

The allowlists below are the *reduced* views. The filter keeps only these fields
(plus the structural ``resourceType``/``id``); everything else — addresses,
telecom, observation values, participants — is removed, not blanked, so a
restricted caller cannot infer presence from an empty field.
"""

from __future__ import annotations

from typing import Any

# The role that grants full field access. Absent it, the reduced view applies.
FULL_ACCESS_ROLE = "phi:full"

_ALWAYS = frozenset({"resourceType", "id"})

_LIMITED_FIELDS: dict[str, frozenset[str]] = {
    # Demographics for matching — no contact info, marital/deceased status.
    "Patient": frozenset({"identifier", "name", "gender", "birthDate"}),
    # Existence + timing/type — no participants or identifiers.
    "Encounter": frozenset({"status", "class", "period"}),
    # That a result exists and what was measured — NOT the value/interpretation.
    "Observation": frozenset({"status", "code", "effectiveDateTime"}),
    # That an order exists and what was ordered — NOT subject/requester.
    "ServiceRequest": frozenset({"status", "intent", "code"}),
}


def apply_minimum_necessary(
    resource_type: str, resource: dict[str, Any], *, full_access: bool
) -> dict[str, Any]:
    """Return ``resource`` filtered to the caller's permitted fields.

    Full-access callers get the resource unchanged. Otherwise only the reduced
    allowlist for the resource type survives (unknown types default to id-only).
    """
    if full_access:
        return resource
    allowed = _ALWAYS | _LIMITED_FIELDS.get(resource_type, frozenset())
    return {key: value for key, value in resource.items() if key in allowed}
