"""File-drop HL7 v2 ingestion transport.

Maps to a file-drop edge in docs/DESIGN.md 1 — a third inbound transport
alongside the MLLP socket (``listener``) and HTTP (``gateway.api.ingest``). A
poll loop watches an inbox directory, feeds each dropped HL7 v2 file through the
same shared ``ingest`` pipeline (parse -> route -> map -> encrypted persist ->
acknowledge), writes the HL7 ACK next to the outcome, and moves the source file
to a ``processed`` or ``failed`` directory. Nothing is deleted — an operator can
always inspect what arrived and how it was answered.

Portability (ADR-003): pure ``pathlib`` + a poll loop, no OS-specific inotify, so
it runs identically on Linux, a container volume, or a Windows-mounted share.

Delivery contract: the watched glob must match only *complete* files. Senders
should write to a temporary name and atomically rename into place (or drop into
a staging dir and move in); the watcher additionally skips empty files to avoid
racing a partial write.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from hip.messaging.hl7 import ack
from hip.messaging.hl7.listener import SessionFactory, ingest
from hip.observability.logging import get_logger
from hip.security.blind_index import BlindIndexer
from hip.security.keymanager import KeyManager

logger = get_logger("hip.messaging.hl7.filedrop")

_DEFAULT_GLOB = "*.hl7"
_DEFAULT_POLL_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class FileOutcome:
    """Result of ingesting one dropped file (control-plane only — no PHI)."""

    source: Path
    accepted: bool
    moved_to: Path
    ack_path: Path


class FileDropWatcher:
    """Poll an inbox directory and ingest each dropped HL7 v2 file.

    Pass a ``session_factory``/``key_manager`` to persist accepted messages; omit
    them to run map-only (the same degradation as the MLLP listener). The
    ``processed``/``failed`` directories default to siblings of the inbox and are
    created on start.
    """

    def __init__(  # noqa: PLR0913, PLR0917 - cohesive keyword-only wiring, mirrors MLLPListener
        self,
        inbox: Path,
        *,
        processed: Path | None = None,
        failed: Path | None = None,
        session_factory: SessionFactory | None = None,
        key_manager: KeyManager | None = None,
        blind_indexer: BlindIndexer | None = None,
        glob: str = _DEFAULT_GLOB,
        poll_interval: float = _DEFAULT_POLL_SECONDS,
    ) -> None:
        self.inbox = inbox
        self.processed = processed if processed is not None else inbox.parent / "processed"
        self.failed = failed if failed is not None else inbox.parent / "failed"
        self._session_factory = session_factory
        self._key_manager = key_manager
        self._blind_indexer = blind_indexer
        self._glob = glob
        self._poll_interval = poll_interval

    def _ensure_dirs(self) -> None:
        for directory in (self.inbox, self.processed, self.failed):
            directory.mkdir(parents=True, exist_ok=True)

    def _pending(self) -> list[Path]:
        """Complete, non-empty files awaiting ingestion, oldest first."""
        files = [p for p in self.inbox.glob(self._glob) if p.is_file() and p.stat().st_size > 0]
        return sorted(files, key=lambda p: p.stat().st_mtime)

    @staticmethod
    def _unique(target: Path) -> Path:
        """A non-colliding path in the destination dir (timestamp suffix on clash)."""
        if not target.exists():
            return target
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
        return target.with_name(f"{target.stem}.{stamp}{target.suffix}")

    async def process_one(self, path: Path) -> FileOutcome:
        """Ingest a single file, write its ACK, and move the source aside.

        A non-decodable file is answered with an ``AR`` NACK and routed to
        ``failed`` — same "never drop, always answer" contract as MLLP.
        """
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            ack_message = ack.build_nack_unparseable("INVALID_ENCODING", "file is not valid UTF-8")
            accepted = False
        else:
            result = await ingest(
                raw, self._session_factory, self._key_manager, self._blind_indexer
            )
            ack_message = result.ack_message
            accepted = result.ack_code is ack.AckCode.AA

        destination_dir = self.processed if accepted else self.failed
        moved_to = self._unique(destination_dir / path.name)
        path.rename(moved_to)
        ack_path = moved_to.with_suffix(moved_to.suffix + ".ack")
        ack_path.write_text(ack_message, encoding="utf-8")

        logger.info(
            "file_ingested",
            source=path.name,
            accepted=accepted,
            moved_to=str(moved_to.parent.name),
        )
        return FileOutcome(source=path, accepted=accepted, moved_to=moved_to, ack_path=ack_path)

    async def poll_once(self) -> list[FileOutcome]:
        """Process every file currently pending. Returns each file's outcome."""
        self._ensure_dirs()
        outcomes: list[FileOutcome] = []
        for path in self._pending():
            outcomes.append(await self.process_one(path))
        return outcomes

    async def run(self, *, stop: asyncio.Event | None = None) -> None:  # pragma: no cover
        """Poll the inbox until cancelled or ``stop`` is set (operational loop)."""
        self._ensure_dirs()
        logger.info("filedrop_watcher_started", inbox=str(self.inbox))
        while stop is None or not stop.is_set():
            await self.poll_once()
            await asyncio.sleep(self._poll_interval)
