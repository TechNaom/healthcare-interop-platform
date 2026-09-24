"""File-drop transport unit tests — map-only, no DB.

Drops synthetic HL7 files (ADR-005) into a tmp inbox and asserts the watcher
routes them: an accepted ADT lands in ``processed`` with an ``AA`` ACK; a
malformed message and an unsupported type land in ``failed`` with an ``AR`` ACK;
and every file is answered and moved (never dropped). Runs in-process without a
socket or database (session_factory omitted -> map-only), mirroring the MLLP
listener's degradation.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from hip.messaging.hl7.filedrop import FileDropWatcher

pytestmark = pytest.mark.unit


def _watcher(inbox: Path) -> FileDropWatcher:
    return FileDropWatcher(inbox)


def _drop(inbox: Path, name: str, content: str) -> Path:
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / name
    path.write_text(content, encoding="utf-8")
    return path


def test_accepted_message_goes_to_processed(tmp_path: Path, adt_a01: str) -> None:
    inbox = tmp_path / "inbox"
    _drop(inbox, "adt.hl7", adt_a01)
    watcher = _watcher(inbox)

    outcomes = asyncio.run(watcher.poll_once())

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.accepted is True
    assert outcome.moved_to.parent == watcher.processed
    assert not (inbox / "adt.hl7").exists()  # source moved, not left behind
    assert "MSA|AA" in outcome.ack_path.read_text(encoding="utf-8")


def test_malformed_message_goes_to_failed(tmp_path: Path, malformed_no_msh: str) -> None:
    inbox = tmp_path / "inbox"
    _drop(inbox, "bad.hl7", malformed_no_msh)
    watcher = _watcher(inbox)

    outcomes = asyncio.run(watcher.poll_once())

    assert outcomes[0].accepted is False
    assert outcomes[0].moved_to.parent == watcher.failed
    assert "MSA|AR" in outcomes[0].ack_path.read_text(encoding="utf-8")


def test_unsupported_type_is_rejected(tmp_path: Path, mdm_t01: str) -> None:
    inbox = tmp_path / "inbox"
    _drop(inbox, "mdm.hl7", mdm_t01)
    watcher = _watcher(inbox)

    outcomes = asyncio.run(watcher.poll_once())

    assert outcomes[0].accepted is False
    assert outcomes[0].moved_to.parent == watcher.failed


def test_empty_and_nonmatching_files_are_skipped(tmp_path: Path, adt_a01: str) -> None:
    inbox = tmp_path / "inbox"
    _drop(inbox, "empty.hl7", "")  # zero bytes -> partial-write guard skips it
    _drop(inbox, "notes.txt", adt_a01)  # wrong glob -> ignored
    watcher = _watcher(inbox)

    outcomes = asyncio.run(watcher.poll_once())

    assert outcomes == []
    assert (inbox / "empty.hl7").exists()
    assert (inbox / "notes.txt").exists()


def test_name_collision_does_not_overwrite(tmp_path: Path, adt_a01: str) -> None:
    inbox = tmp_path / "inbox"
    watcher = _watcher(inbox)

    _drop(inbox, "dup.hl7", adt_a01)
    first = asyncio.run(watcher.poll_once())[0]
    _drop(inbox, "dup.hl7", adt_a01)
    second = asyncio.run(watcher.poll_once())[0]

    assert first.moved_to != second.moved_to  # second kept, not clobbered
    assert first.moved_to.exists()
    assert second.moved_to.exists()
