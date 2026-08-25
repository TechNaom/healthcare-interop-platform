"""Async MLLP listener — HL7 v2 ingestion transport.

Maps to ``messaging.hl7.listener`` in docs/DESIGN.md 1. An asyncio TCP server
that speaks MLLP: it reassembles framed messages, runs each through the
ingestion pipeline (parse -> route -> acknowledge), and writes the framed
ACK/NACK back. HTTP and file-drop transports are separate later additions; this
is the socket edge.

The pipeline function ``process_raw`` is transport-independent so it can be unit
tested without a socket, and reused by the HTTP/file-drop transports.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from hip.messaging.hl7 import ack, router
from hip.messaging.hl7.mllp import MLLPBuffer, wrap
from hip.messaging.hl7.parser import ParseError, parse

logger = logging.getLogger("hip.messaging.hl7.listener")


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Outcome of processing one inbound message."""

    ack_code: ack.AckCode
    ack_message: str
    reason: str = ""


def process_raw(raw: str) -> IngestResult:
    """Run one raw HL7 message through parse -> route -> acknowledge.

    Never raises for bad input — a parse failure becomes an AR NACK, which is
    the correct HL7 behavior (a malformed message must be answered, not dropped).
    """
    try:
        parsed = parse(raw)
    except ParseError as exc:
        nack = ack.build_nack_unparseable(exc.reason, exc.detail)
        return IngestResult(ack.AckCode.AR, nack, reason=exc.reason)

    decision = router.route(parsed)
    ack_message = ack.build_ack(
        parsed,
        decision.ack_code,
        text=decision.detail,
    )
    return IngestResult(decision.ack_code, ack_message, reason=decision.reason)


class MLLPListener:
    """MLLP TCP server. One ``MLLPBuffer`` per connection handles stream framing."""

    def __init__(self, host: str = "0.0.0.0", port: int = 2575) -> None:  # noqa: S104  # nosec B104
        # Binding all interfaces is the point of a network listener; exposure is
        # controlled at the container/network boundary, and deployment can pass a
        # narrower host. Hence the S104/B104 suppressions above.
        self.host = host
        self.port = port
        self._server: asyncio.Server | None = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        buffer = MLLPBuffer()
        try:
            while data := await reader.read(4096):
                for message in buffer.feed(data):
                    result = process_raw(message)
                    # Never log message content — it is PHI (ADR-005). Log only
                    # the control-plane outcome.
                    logger.info("hl7 message from %s -> %s", peer, result.ack_code.value)
                    writer.write(wrap(result.ack_message))
                    await writer.drain()
        except (ConnectionResetError, asyncio.IncompleteReadError):
            logger.info("connection from %s closed mid-stream", peer)
        finally:
            writer.close()

    async def start(self) -> asyncio.Server:
        """Start serving and return the asyncio server (caller awaits it)."""
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        for sock in self._server.sockets or ():
            logger.info("MLLP listener on %s", sock.getsockname())
        return self._server

    async def serve_forever(self) -> None:
        server = self._server or await self.start()
        async with server:
            await server.serve_forever()


async def _main() -> None:  # pragma: no cover - operational entrypoint
    logging.basicConfig(level=logging.INFO)
    await MLLPListener().serve_forever()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())
