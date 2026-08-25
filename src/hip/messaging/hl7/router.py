"""HL7 message routing by message type.

Maps to ``messaging.hl7.router`` in docs/DESIGN.md 1. Decides what happens to a
parsed message: supported types (ADT/ORM/ORU per SRS 4.1) are accepted for
downstream canonical mapping; anything else is rejected with a reason. The
mapping itself is the ADR-001-gated ``canonical.mapper`` step and is not invoked
here yet.
"""

from __future__ import annotations

from dataclasses import dataclass

from hip.messaging.hl7.ack import AckCode
from hip.messaging.hl7.parser import ParsedMessage

# Message codes this build accepts (SRS 4.1). Trigger-event-level support is a
# later refinement; routing is by code first.
SUPPORTED_MESSAGE_CODES = frozenset({"ADT", "ORM", "ORU"})


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    ack_code: AckCode
    reason: str = ""
    detail: str = ""


def route(parsed: ParsedMessage) -> RoutingDecision:
    """Decide accept/reject for a parsed message."""
    if parsed.message_code not in SUPPORTED_MESSAGE_CODES:
        return RoutingDecision(
            ack_code=AckCode.AR,
            reason="UNSUPPORTED_MESSAGE_TYPE",
            detail=(
                f"{parsed.message_type} not supported; "
                f"expected one of {sorted(SUPPORTED_MESSAGE_CODES)}"
            ),
        )
    # Accepted. Downstream (canonical mapping + persistence) lands in later
    # phases; for now acceptance means "structurally valid and routable".
    return RoutingDecision(ack_code=AckCode.AA)
