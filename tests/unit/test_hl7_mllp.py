"""Unit tests for MLLP framing and stream reassembly."""

from __future__ import annotations

import pytest

from hip.messaging.hl7.mllp import CR, FS, VT, MLLPBuffer, wrap

pytestmark = pytest.mark.unit


def test_wrap_adds_framing_bytes() -> None:
    framed = wrap("MSH|x")
    assert framed[0] == VT
    assert framed[-2] == FS
    assert framed[-1] == CR
    assert framed[1:-2] == b"MSH|x"


def test_buffer_yields_single_complete_message() -> None:
    buf = MLLPBuffer()
    assert list(buf.feed(wrap("HELLO"))) == ["HELLO"]


def test_buffer_reassembles_split_frame() -> None:
    """A message split across two TCP reads is delivered once, whole."""
    framed = wrap("MSH|split")
    buf = MLLPBuffer()
    mid = len(framed) // 2
    assert list(buf.feed(framed[:mid])) == []  # incomplete so far
    assert list(buf.feed(framed[mid:])) == ["MSH|split"]


def test_buffer_handles_multiple_messages_in_one_read() -> None:
    buf = MLLPBuffer()
    payload = wrap("ONE") + wrap("TWO") + wrap("THREE")
    assert list(buf.feed(payload)) == ["ONE", "TWO", "THREE"]


def test_buffer_discards_noise_before_start_byte() -> None:
    buf = MLLPBuffer()
    noise = b"garbage-with-no-start"
    assert list(buf.feed(noise)) == []
    assert list(buf.feed(wrap("CLEAN"))) == ["CLEAN"]
