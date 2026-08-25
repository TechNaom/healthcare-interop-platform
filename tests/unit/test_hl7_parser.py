"""Unit tests for HL7 v2 parsing and MSH extraction."""

from __future__ import annotations

import pytest

from hip.messaging.hl7.parser import ParseError, parse

pytestmark = pytest.mark.unit


def test_parses_valid_adt_and_extracts_msh(adt_a01: str) -> None:
    parsed = parse(adt_a01)
    assert parsed.message_type == "ADT^A01"
    assert parsed.message_code == "ADT"
    assert parsed.trigger_event == "A01"
    assert parsed.control_id == "MSG00001"
    assert parsed.sending_application == "SENDAPP"
    assert parsed.sending_facility == "SENDFAC"
    assert parsed.version == "2.5"


def test_normalizes_newline_segment_separators(adt_a01: str) -> None:
    """Senders using \\n or \\r\\n instead of \\r still parse."""
    assert parse(adt_a01.replace("\r", "\n")).message_code == "ADT"
    assert parse(adt_a01.replace("\r", "\r\n")).message_code == "ADT"


def test_empty_message_rejected() -> None:
    with pytest.raises(ParseError) as exc:
        parse("   ")
    assert exc.value.reason == "EMPTY_MESSAGE"


def test_missing_msh_rejected(malformed_no_msh: str) -> None:
    with pytest.raises(ParseError) as exc:
        parse(malformed_no_msh)
    assert exc.value.reason == "MISSING_MSH"


def test_missing_control_id_rejected() -> None:
    no_ctrl = "MSH|^~\\&|A|B|C|D|20260825101500||ADT^A01||P|2.5\r"
    with pytest.raises(ParseError) as exc:
        parse(no_ctrl)
    assert exc.value.reason == "MISSING_CONTROL_ID"
