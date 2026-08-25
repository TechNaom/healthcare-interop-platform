"""HL7 v2 structural parse and MSH metadata extraction.

Maps to ``messaging.hl7.parser`` in docs/DESIGN.md 1. Uses ``python-hl7`` for
structural parsing and pulls the routing/acknowledgement metadata off MSH. It
does NOT map to the canonical model — that is the ``canonical.mapper`` step,
gated on the ADR-001 model sign-off. A structural failure here raises
``ParseError`` carrying a reason, which the pipeline turns into a NACK.
"""

from __future__ import annotations

from dataclasses import dataclass

import hl7

# HL7 v2 uses <CR> as the segment separator. Tolerate senders that use \n or
# \r\n by normalizing before parsing.
_SEGMENT_CR = "\r"


class ParseError(Exception):
    """Raised when a message can't be structurally parsed. ``reason`` is a short
    machine code; ``detail`` is human-readable."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True, slots=True)
class ParsedMessage:
    """Structural view of an HL7 v2 message plus the fields needed to route and
    acknowledge it. Segment-level access stays available via ``message``."""

    message_type: str  # MSH-9 full, e.g. "ADT^A01"
    message_code: str  # MSH-9.1, e.g. "ADT"
    trigger_event: str  # MSH-9.2, e.g. "A01"
    control_id: str  # MSH-10
    sending_application: str  # MSH-3
    sending_facility: str  # MSH-4
    receiving_application: str  # MSH-5
    receiving_facility: str  # MSH-6
    version: str  # MSH-12
    raw: str
    message: hl7.Message


def _field(msh: hl7.Segment, index: int) -> str:
    """Best-effort string for an MSH field; empty string if absent."""
    try:
        return str(msh[index]).strip()
    except (IndexError, KeyError):
        return ""


def parse(raw: str) -> ParsedMessage:
    """Parse a raw HL7 v2 message. Raises ``ParseError`` on structural failure."""
    text = raw.replace("\r\n", _SEGMENT_CR).replace("\n", _SEGMENT_CR).strip()
    if not text:
        raise ParseError("EMPTY_MESSAGE", "no content")
    if not text.startswith("MSH"):
        raise ParseError("MISSING_MSH", "message does not start with an MSH segment")

    try:
        message = hl7.parse(text)
    except Exception as exc:  # python-hl7 raises assorted errors on bad input
        raise ParseError("UNPARSEABLE", str(exc)) from exc

    try:
        msh = message.segment("MSH")
    except KeyError as exc:
        raise ParseError("MISSING_MSH", "no MSH segment after parse") from exc

    message_type = _field(msh, 9)
    if not message_type:
        raise ParseError("MISSING_MSG_TYPE", "MSH-9 (message type) is empty")
    control_id = _field(msh, 10)
    if not control_id:
        raise ParseError("MISSING_CONTROL_ID", "MSH-10 (message control id) is empty")

    code, _, trigger = message_type.partition("^")
    return ParsedMessage(
        message_type=message_type,
        message_code=code,
        trigger_event=trigger,
        control_id=control_id,
        sending_application=_field(msh, 3),
        sending_facility=_field(msh, 4),
        receiving_application=_field(msh, 5),
        receiving_facility=_field(msh, 6),
        version=_field(msh, 12),
        raw=raw,
        message=message,
    )
