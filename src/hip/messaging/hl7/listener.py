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
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hip.messaging.canonical import mapper
from hip.messaging.canonical.mapper import CanonicalBundle, MappingError
from hip.messaging.canonical.model import DeadLetterMessage, FailureReason, FailureStage
from hip.messaging.hl7 import ack, router
from hip.messaging.hl7.mllp import MLLPBuffer, wrap
from hip.messaging.hl7.parser import ParsedMessage, ParseError, parse
from hip.observability.logging import configure_logging, get_logger
from hip.persistence.db import make_engine, make_sessionmaker
from hip.persistence.dead_letter_repo import DeadLetterRepository
from hip.persistence.deid_repo import DeidRepository
from hip.persistence.phi_repo import PhiRepository
from hip.security.deid import deidentify_patient
from hip.security.keymanager import KeyManager, keymanager_from_env

logger = get_logger("hip.messaging.hl7.listener")

SessionFactory = async_sessionmaker[AsyncSession]


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Outcome of processing one inbound message."""

    ack_code: ack.AckCode
    ack_message: str
    reason: str = ""
    detail: str = ""
    bundle: CanonicalBundle | None = None
    parsed: ParsedMessage | None = None
    failure_stage: FailureStage | None = None


def process_raw(raw: str) -> IngestResult:
    """Parse -> route -> map (pure; no I/O).

    Never raises for bad input. Each stage failure yields the right NACK and a
    ``failure_stage`` so the caller can dead-letter it: parse -> AR (parse),
    unsupported type -> AR (validate), mapping -> AE (transform). A malformed
    message is always answered, never dropped (docs/DATA_MODEL.md stages).
    """
    try:
        parsed = parse(raw)
    except ParseError as exc:
        nack = ack.build_nack_unparseable(exc.reason, exc.detail)
        return IngestResult(
            ack.AckCode.AR,
            nack,
            reason=exc.reason,
            detail=exc.detail,
            failure_stage=FailureStage.parse,
        )

    decision = router.route(parsed)
    if decision.ack_code is not ack.AckCode.AA:
        nack = ack.build_ack(parsed, decision.ack_code, text=decision.detail)
        return IngestResult(
            decision.ack_code,
            nack,
            reason=decision.reason,
            detail=decision.detail,
            parsed=parsed,
            failure_stage=FailureStage.validate,
        )

    try:
        bundle = mapper.map_message(parsed)
    except MappingError as exc:
        nack = ack.build_ack(parsed, ack.AckCode.AE, text=f"{exc.reason} {exc.detail}".strip())
        return IngestResult(
            ack.AckCode.AE,
            nack,
            reason=exc.reason,
            detail=exc.detail,
            parsed=parsed,
            failure_stage=FailureStage.transform,
        )

    ack_message = ack.build_ack(parsed, ack.AckCode.AA)
    return IngestResult(ack.AckCode.AA, ack_message, bundle=bundle, parsed=parsed)


async def _store_dead_letter(
    session_factory: SessionFactory,
    key_manager: KeyManager,
    raw: str,
    result: IngestResult,
) -> None:
    """Persist an unprocessable message (encrypted). Never raises — a dead-letter
    write failure is logged, not propagated (the sender already has the NACK)."""
    if result.failure_stage is None:
        return
    parsed = result.parsed
    source = f"{parsed.sending_application}/{parsed.sending_facility}" if parsed else None
    message = DeadLetterMessage(
        received_at=datetime.now(UTC),
        source=source,
        raw_message=raw,
        failure_stage=result.failure_stage,
        failure_reason=FailureReason(code=result.reason, detail=result.detail or None),
        message_control_id=parsed.control_id if parsed else None,
    )
    try:
        async with session_factory() as session:
            await DeadLetterRepository(session, key_manager).save(message)
            await session.commit()
    except SQLAlchemyError as exc:
        logger.error("dead_letter_store_failed", error=type(exc).__name__)  # never log PHI


async def ingest(
    raw: str,
    session_factory: SessionFactory | None = None,
    key_manager: KeyManager | None = None,
) -> IngestResult:
    """Ingest one message and log the outcome with non-PHI fields only.

    Wraps ``_run_ingest``; the log carries control-plane facts (ack, stage,
    reason, message-control-id, sending system) — never patient content
    (docs/TEST_STRATEGY.md no-PHI-in-logs).
    """
    result = await _run_ingest(raw, session_factory, key_manager)
    parsed = result.parsed
    logger.info(
        "message_ingested",
        ack=result.ack_code.value,
        stage=result.failure_stage.value if result.failure_stage else None,
        reason=result.reason or None,
        control_id=parsed.control_id if parsed else None,
        source=(f"{parsed.sending_application}/{parsed.sending_facility}" if parsed else None),
    )
    return result


async def _run_ingest(
    raw: str,
    session_factory: SessionFactory | None,
    key_manager: KeyManager | None,
) -> IngestResult:
    """Full ingestion: ``process_raw``, then persist an accepted bundle (encrypted)
    or dead-letter an unprocessable one.

    Data + audit commit in one transaction. A malformed/unsupported/transform
    failure is stored (encrypted) in the dead-letter store, not lost. With no
    ``session_factory`` this is map-only. Fail-closed: without a ``key_manager``
    nothing PHI-bearing (bundle or raw dead-letter) is stored.
    """
    result = process_raw(raw)
    if session_factory is None:
        return result  # map-only mode: no persistence, no dead-letter

    if key_manager is None:
        # Cannot store PHI (bundle or raw payload) unencrypted -> fail closed.
        if result.ack_code is ack.AckCode.AA and result.bundle is not None:
            parsed = result.parsed
            nack = (
                ack.build_ack(parsed, ack.AckCode.AE, text="ENCRYPTION_NOT_CONFIGURED")
                if parsed is not None
                else ack.build_nack_unparseable("ENCRYPTION_NOT_CONFIGURED")
            )
            return IngestResult(
                ack.AckCode.AE, nack, reason="ENCRYPTION_NOT_CONFIGURED", parsed=parsed
            )
        return result

    if result.ack_code is ack.AckCode.AA and result.bundle is not None:
        try:
            async with session_factory() as session:
                await PhiRepository(session, key_manager).save_bundle(result.bundle)
                # De-identified copy into the separate store, same transaction.
                if result.bundle.patient is not None:
                    await DeidRepository(session).save(deidentify_patient(result.bundle.patient))
                await session.commit()
        except SQLAlchemyError as exc:
            logger.error("persist_failed", error=type(exc).__name__)  # never log PHI
            parsed = result.parsed
            nack = (
                ack.build_ack(parsed, ack.AckCode.AE, text="PERSIST_FAILED")
                if parsed is not None
                else ack.build_nack_unparseable("PERSIST_FAILED")
            )
            fail_result = IngestResult(
                ack.AckCode.AE,
                nack,
                reason="PERSIST_FAILED",
                parsed=parsed,
                failure_stage=FailureStage.persist,
            )
            await _store_dead_letter(session_factory, key_manager, raw, fail_result)
            return fail_result
        return result

    # NACK (parse / unsupported / transform): dead-letter the raw message.
    await _store_dead_letter(session_factory, key_manager, raw, result)
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
        key_manager: KeyManager | None = None,
    ) -> None:
        # Binding all interfaces is the point of a network listener; exposure is
        # controlled at the container/network boundary. Hence the S104/B104 waivers.
        self.host = host
        self.port = port
        self._session_factory = session_factory
        self._key_manager = key_manager
        self._server: asyncio.Server | None = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        buffer = MLLPBuffer()
        try:
            while data := await reader.read(4096):
                for message in buffer.feed(data):
                    # ingest() logs the outcome (non-PHI); write the framed ACK back.
                    result = await ingest(message, self._session_factory, self._key_manager)
                    writer.write(wrap(result.ack_message))
                    await writer.drain()
        except (ConnectionResetError, asyncio.IncompleteReadError):
            logger.info("connection_closed", peer=str(peer))
        finally:
            writer.close()

    async def start(self) -> asyncio.Server:
        """Start serving and return the asyncio server (caller awaits it)."""
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        for sock in self._server.sockets or ():
            logger.info("mllp_listener_started", address=str(sock.getsockname()))
        return self._server

    async def serve_forever(self) -> None:
        server = self._server or await self.start()
        async with server:
            await server.serve_forever()


async def _main() -> None:  # pragma: no cover - operational entrypoint
    configure_logging()
    engine = make_engine()
    session_factory = make_sessionmaker(engine)
    key_manager = keymanager_from_env()
    await MLLPListener(session_factory=session_factory, key_manager=key_manager).serve_forever()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())
