"""Async MLLP listener — HL7 v2 ingestion transport.

Maps to ``messaging.hl7.listener`` in docs/DESIGN.md 1. An asyncio TCP server
that speaks MLLP: it reassembles framed messages, runs each through the
ingestion pipeline (parse -> route -> map -> persist -> acknowledge), and writes
the framed ACK/NACK back. HTTP and file-drop transports are separate later
additions; this is the socket edge.

``process_raw`` (parse/route/map, no I/O) is transport-independent and pure, so
it unit-tests without a socket or DB. ``ingest`` adds the persistence step and is
what the server calls; if no session factory is supplied it degrades to
map-only, which keeps the mapping path testable in isolation.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hip.messaging.canonical import mapper
from hip.messaging.canonical.mapper import CanonicalBundle, MappingError
from hip.messaging.hl7 import ack, router
from hip.messaging.hl7.mllp import MLLPBuffer, wrap
from hip.messaging.hl7.parser import ParsedMessage, ParseError, parse
from hip.persistence.db import make_engine, make_sessionmaker
from hip.persistence.phi_repo import PhiRepository

logger = logging.getLogger("hip.messaging.hl7.listener")

SessionFactory = async_sessionmaker[AsyncSession]


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Outcome of processing one inbound message."""

    ack_code: ack.AckCode
    ack_message: str
    reason: str = ""
    bundle: CanonicalBundle | None = None
    parsed: ParsedMessage | None = None


def process_raw(raw: str) -> IngestResult:
    """Parse -> route -> map (pure; no I/O).

    Never raises for bad input. Each stage failure yields the right NACK:
    parse -> AR, unsupported type -> AR, mapping/transform -> AE. A malformed
    message is always answered, never dropped (docs/DATA_MODEL.md stages).
    """
    try:
        parsed = parse(raw)
    except ParseError as exc:
        nack = ack.build_nack_unparseable(exc.reason, exc.detail)
        return IngestResult(ack.AckCode.AR, nack, reason=exc.reason)

    decision = router.route(parsed)
    if decision.ack_code is not ack.AckCode.AA:
        nack = ack.build_ack(parsed, decision.ack_code, text=decision.detail)
        return IngestResult(decision.ack_code, nack, reason=decision.reason, parsed=parsed)

    try:
        bundle = mapper.map_message(parsed)
    except MappingError as exc:
        nack = ack.build_ack(parsed, ack.AckCode.AE, text=f"{exc.reason} {exc.detail}".strip())
        return IngestResult(ack.AckCode.AE, nack, reason=exc.reason, parsed=parsed)

    ack_message = ack.build_ack(parsed, ack.AckCode.AA)
    return IngestResult(ack.AckCode.AA, ack_message, bundle=bundle, parsed=parsed)


async def ingest(raw: str, session_factory: SessionFactory | None = None) -> IngestResult:
    """Full ingestion: ``process_raw`` then persist an accepted bundle.

    Data and its audit trail commit in one transaction (PhiRepository). A
    persistence failure becomes an AE NACK (persist stage) rather than a lost
    message. With no ``session_factory`` this is map-only (AA without storing).
    """
    result = process_raw(raw)
    if session_factory is None or result.ack_code is not ack.AckCode.AA or result.bundle is None:
        return result

    try:
        async with session_factory() as session:
            await PhiRepository(session).save_bundle(result.bundle)
            await session.commit()
    except SQLAlchemyError as exc:
        logger.error("persist failed: %s", type(exc).__name__)  # never log PHI
        parsed = result.parsed
        nack = (
            ack.build_ack(parsed, ack.AckCode.AE, text="PERSIST_FAILED")
            if parsed is not None
            else ack.build_nack_unparseable("PERSIST_FAILED")
        )
        return IngestResult(ack.AckCode.AE, nack, reason="PERSIST_FAILED", parsed=parsed)

    return result


class MLLPListener:
    """MLLP TCP server. One ``MLLPBuffer`` per connection handles stream framing.

    Pass a ``session_factory`` to persist accepted messages; omit it (e.g. in a
    parse/route smoke test) to run the pipeline without a database.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",  # noqa: S104  # nosec B104
        port: int = 2575,
        *,
        session_factory: SessionFactory | None = None,
    ) -> None:
        # Binding all interfaces is the point of a network listener; exposure is
        # controlled at the container/network boundary. Hence the S104/B104 waivers.
        self.host = host
        self.port = port
        self._session_factory = session_factory
        self._server: asyncio.Server | None = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        buffer = MLLPBuffer()
        try:
            while data := await reader.read(4096):
                for message in buffer.feed(data):
                    result = await ingest(message, self._session_factory)
                    # Never log message content — it is PHI (ADR-005).
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
    engine = make_engine()
    session_factory = make_sessionmaker(engine)
    await MLLPListener(session_factory=session_factory).serve_forever()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())
