"""Integration: unprocessable messages land in the dead-letter store (encrypted).

A malformed or unsupported message must be NACKed AND kept — not silently
dropped — so it can be triaged/reprocessed. The raw payload is PHI, so it is
stored encrypted. Real Postgres; synthetic HL7 only (ADR-005).
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from hip.messaging.hl7.listener import ingest
from hip.persistence.db import make_engine, make_sessionmaker
from hip.persistence.models import DeadLetterRow
from hip.security.keymanager import KeyManager

pytestmark = pytest.mark.integration


async def _ingest_and_fetch(url: str, raw: str, km: KeyManager) -> tuple[str, list[DeadLetterRow]]:
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)
    result = await ingest(raw, session_factory, km)
    async with session_factory() as session:
        rows = list((await session.execute(select(DeadLetterRow))).scalars())
    await engine.dispose()
    return result.ack_code.value, rows


def test_malformed_message_dead_lettered_encrypted(clean_db: str, key_manager: KeyManager) -> None:
    raw = "PID|1||MRN12345^^^HOSP^MR||DOE^JANE\r"  # no MSH -> parse failure
    ack_code, rows = asyncio.run(_ingest_and_fetch(clean_db, raw, key_manager))

    assert ack_code == "AR"
    assert len(rows) == 1
    row = rows[0]
    assert row.failure_stage == "parse"
    assert row.failure_reason_code == "MISSING_MSH"
    # Raw payload stored encrypted — plaintext PHI absent, decrypts back correctly.
    assert b"MRN12345" not in row.raw_ciphertext
    assert b"DOE" not in row.raw_ciphertext
    assert b"MRN12345" in key_manager.decrypt(row.raw_ciphertext)


def test_unsupported_type_dead_lettered(
    clean_db: str, mdm_t01: str, key_manager: KeyManager
) -> None:
    ack_code, rows = asyncio.run(_ingest_and_fetch(clean_db, mdm_t01, key_manager))
    assert ack_code == "AR"
    assert len(rows) == 1
    assert rows[0].failure_stage == "validate"
    assert rows[0].failure_reason_code == "UNSUPPORTED_MESSAGE_TYPE"
    assert rows[0].message_control_id == "MSG00003"  # MSH-10 recovered


def test_valid_message_is_not_dead_lettered(
    clean_db: str, adt_a01: str, key_manager: KeyManager
) -> None:
    ack_code, rows = asyncio.run(_ingest_and_fetch(clean_db, adt_a01, key_manager))
    assert ack_code == "AA"
    assert rows == []
