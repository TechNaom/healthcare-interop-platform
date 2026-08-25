"""HL7 v2 acknowledgement (ACK/NACK) construction.

An ACK is itself an HL7 message: an MSH (with sender/receiver swapped from the
original) plus an MSA carrying the acknowledgement code and the original
message's control id. Codes (HL7 table 0008):

    AA — Application Accept   (message accepted)
    AE — Application Error    (rejected; sender may retry after fixing)
    AR — Application Reject    (rejected; do not retry as-is)

docs/DESIGN.md 4 (error handling / ACK-NACK strategy).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from hip.messaging.hl7.parser import ParsedMessage

_ENCODING_CHARS = r"^~\&"
_THIS_APPLICATION = "HIP"
_THIS_FACILITY = "HIP_GATEWAY"


class AckCode(StrEnum):
    AA = "AA"  # accept
    AE = "AE"  # error
    AR = "AR"  # reject


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S")


def build_ack(
    parsed: ParsedMessage,
    code: AckCode,
    text: str = "",
    *,
    control_id: str | None = None,
) -> str:
    """Build an ACK for a successfully-parsed message.

    Sender/receiver are swapped so the ACK is addressed back to the origin.
    ``control_id`` overrides the ACK's own MSH-10 (defaults to reusing the
    original's, which is conventional and lets the sender correlate).
    """
    ack_control = control_id or parsed.control_id
    msh = "|".join(
        [
            "MSH",
            _ENCODING_CHARS,
            _THIS_APPLICATION,
            _THIS_FACILITY,
            parsed.sending_application,
            parsed.sending_facility,
            _timestamp(),
            "",
            f"ACK^{parsed.trigger_event}" if parsed.trigger_event else "ACK",
            ack_control,
            "P",
            parsed.version or "2.5",
        ]
    )
    msa = "|".join(["MSA", code.value, parsed.control_id, text]).rstrip("|")
    return f"{msh}\r{msa}\r"


def build_nack_unparseable(reason: str, text: str = "", *, control_id: str = "") -> str:
    """Build a reject ACK when the inbound message couldn't be parsed at all.

    With no usable MSH we can't address the ACK back to a real sender, so this
    is a minimal AR referencing whatever control id we could recover (often
    none). ``reason`` becomes the MSA-3 code prefix for the sender's logs.
    """
    msh = "|".join(
        [
            "MSH",
            _ENCODING_CHARS,
            _THIS_APPLICATION,
            _THIS_FACILITY,
            "",
            "",
            _timestamp(),
            "",
            "ACK",
            control_id or "UNKNOWN",
            "P",
            "2.5",
        ]
    )
    detail = f"{reason} {text}".strip()
    msa = "|".join(["MSA", AckCode.AR.value, control_id, detail]).rstrip("|")
    return f"{msh}\r{msa}\r"
