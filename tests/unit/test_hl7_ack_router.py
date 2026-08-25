"""Unit tests for ACK/NACK construction, routing, and the ingest pipeline."""

from __future__ import annotations

import pytest

from hip.messaging.hl7.ack import AckCode, build_ack, build_nack_unparseable
from hip.messaging.hl7.listener import process_raw
from hip.messaging.hl7.parser import parse
from hip.messaging.hl7.router import route

pytestmark = pytest.mark.unit


def test_ack_swaps_sender_and_receiver(adt_a01: str) -> None:
    parsed = parse(adt_a01)
    ack_text = build_ack(parsed, AckCode.AA)
    lines = ack_text.split("\r")
    msh_fields = lines[0].split("|")
    # Original sender (SENDAPP/SENDFAC) becomes the ACK's receiver.
    assert msh_fields[4] == "SENDAPP"
    assert msh_fields[5] == "SENDFAC"
    # MSA references the original control id with the AA code.
    msa_fields = lines[1].split("|")
    assert msa_fields[0] == "MSA"
    assert msa_fields[1] == "AA"
    assert msa_fields[2] == "MSG00001"


def test_nack_unparseable_is_a_reject() -> None:
    nack = build_nack_unparseable("MISSING_MSH", "no MSH segment")
    msa = [line for line in nack.split("\r") if line.startswith("MSA")][0]
    assert msa.split("|")[1] == "AR"
    assert "MISSING_MSH" in nack


def test_route_accepts_supported_types(adt_a01: str, oru_r01: str) -> None:
    assert route(parse(adt_a01)).ack_code is AckCode.AA
    assert route(parse(oru_r01)).ack_code is AckCode.AA


def test_route_rejects_unsupported_type(mdm_t01: str) -> None:
    decision = route(parse(mdm_t01))
    assert decision.ack_code is AckCode.AR
    assert decision.reason == "UNSUPPORTED_MESSAGE_TYPE"


def test_pipeline_accepts_valid_adt(adt_a01: str) -> None:
    result = process_raw(adt_a01)
    assert result.ack_code is AckCode.AA
    assert "MSA|AA|MSG00001" in result.ack_message


def test_pipeline_rejects_unsupported(mdm_t01: str) -> None:
    result = process_raw(mdm_t01)
    assert result.ack_code is AckCode.AR
    assert result.reason == "UNSUPPORTED_MESSAGE_TYPE"


def test_pipeline_nacks_malformed_without_raising(malformed_no_msh: str) -> None:
    """A malformed message is answered with a NACK, never dropped or crashed."""
    result = process_raw(malformed_no_msh)
    assert result.ack_code is AckCode.AR
    assert result.reason == "MISSING_MSH"
