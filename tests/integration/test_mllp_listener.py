"""Integration: the MLLP listener accepts a real TCP connection and ACKs.

Exercises the full socket edge (framing + parse + route + ack) over a loopback
connection on an ephemeral port. No containers needed, so it runs on every PR.
Synthetic HL7 only (ADR-005). Uses asyncio.run rather than pytest-asyncio to
keep the dependency set minimal.
"""

from __future__ import annotations

import asyncio

import pytest

from hip.messaging.hl7.listener import MLLPListener
from hip.messaging.hl7.mllp import MLLPBuffer, wrap

pytestmark = pytest.mark.integration


async def _roundtrip(message: str) -> str:
    listener = MLLPListener(host="127.0.0.1", port=0)  # 0 = ephemeral port
    server: asyncio.Server = await listener.start()
    assert server.sockets
    port = server.sockets[0].getsockname()[1]

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(wrap(message))
        await writer.drain()

        buf = MLLPBuffer()
        acks: list[str] = []
        while not acks:
            data = await asyncio.wait_for(reader.read(4096), timeout=5)
            if not data:
                break
            acks.extend(buf.feed(data))
        return acks[0]
    finally:
        writer.close()
        server.close()
        await server.wait_closed()


def test_listener_acks_valid_adt(adt_a01: str) -> None:
    ack = asyncio.run(_roundtrip(adt_a01))
    assert "MSA|AA|MSG00001" in ack


def test_listener_nacks_unsupported_type(mdm_t01: str) -> None:
    ack = asyncio.run(_roundtrip(mdm_t01))
    assert "MSA|AR" in ack
